#
# Based on:
# Tornado Proxy
# https://github.com/senko/tornado-proxy/blob/master/tornado_proxy/proxy.py
#
# The original license of "Tornado Proxy" follows below:
#
# Copyright (C) 2012 Senko Rasic <senko.rasic@dobarkod.hr>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Research:
# - https://www.cloudflare.com/learning/cdn/glossary/reverse-proxy/
# - https://www.researchgate.net/publication/221034753_Reverse_Proxy_Patterns
# - https://tools.ietf.org/html/rfc7239
# - http://nginx.org/en/docs/http/ngx_http_realip_module.html
# - https://www.tornadoweb.org/en/stable/httputil.html#tornado.httputil.HTTPServerRequest
#

import logging
import os
import time

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.routing
import tornado.httpclient
import tornado.httputil
import traceback
from tornado import websocket, ioloop
from tornado.websocket import websocket_connect

from riptide.config.loader import load_projects
from riptide_proxy.autostart import AutostartHandler
from riptide_proxy.project_loader import resolve_project, extract_names_from, RuntimeStorage, get_all_projects, \
    resolve_container_address

logger = logging.getLogger('tornado_proxy')

logger.setLevel(logging.DEBUG)


class RiptideNoWebSocketMatcher(tornado.routing.PathMatches):
    def match(self, request):
        """ Match path but ONLY non-Websocket requests """
        if "Upgrade" in request.headers and request.headers["Upgrade"] == "websocket":
            return None
        return super().match(request)


class ProxyHandler(tornado.web.RequestHandler):

    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS")

    def __init__(self, application, request, config, engine, runtime_storage, **kwargs):
        """
        TODO
        :raises: FileNotFoundError if the system config was not found
        :raises: schema.SchemaError on validation errors
        """
        super().__init__(application, request, **kwargs)
        self.config = config
        self.engine = engine
        self.runtime_storage = runtime_storage

    def compute_etag(self):
        return None  # disable tornado Etag

    def initialize(self):
        self.request.__riptide_retried = False

    async def get(self):

        project_name, request_service_name = extract_names_from(self.request, self.config["url"])
        if project_name is None:
            self.pp_landing_page()
            return

        try:
            project, resolved_service_name = resolve_project(project_name, request_service_name, self.runtime_storage, logger)

            if project:
                if not resolved_service_name:
                    if not request_service_name:
                        # Load main service if service_name not set
                        resolved_service_name = project["app"].get_service_by_role("main")["$name"]
                        if not resolved_service_name:
                            self.pp_no_main_service(project)
                            return
                    else:
                        self.pp_service_not_found(project, request_service_name)
                        return
                # Resolve address and proxy the request
                address = resolve_container_address(project, resolved_service_name, self.engine, self.runtime_storage, logger)
                if address:
                    await self.reverse_proxy(project, resolved_service_name, address)
                elif self.config["autostart"]:
                    self.pp_start_project(project, resolved_service_name)
                else:
                    self.pp_project_not_started(project, resolved_service_name)
            else:
                self.pp_project_not_found(project_name)
        except Exception as err:
            self.pp_500(project_name, request_service_name, err, traceback.format_exc())
            return

    async def post(self):
        return await self.get()

    async def head(self):
        return await self.get()

    async def delete(self):
        return await self.get()

    async def patch(self,):
        return await self.get()

    async def put(self):
        return await self.get()

    async def options(self):
        return await self.get()

    async def reverse_proxy(self, project, service_name, address):
        logger.debug('Handle %s request to %s (%s)', self.request.method, project["name"], address)

        client = tornado.httpclient.AsyncHTTPClient()

        body = self.request.body
        headers = self.request.headers.copy()

        # Proxy Headers
        headers.add('X-Real-Ip', self.request.remote_ip)
        headers.add('X-Forwarded-For', self.request.remote_ip)
        headers.add('X-Forwarded-Proto', self.request.protocol)
        headers.add('X-Scheme', self.request.protocol)

        if not body:
            body = None

        try:
            # Send request
            req = tornado.httpclient.HTTPRequest(
                address + self.request.uri,
                method=self.request.method,
                body=body,
                headers=headers,
                follow_redirects=False,
                connect_timeout=20,  # todo configurable
                request_timeout=6000,  # todo configurable
            )
            response = await client.fetch(req)
            self.proxy_handle_response(response)
        except tornado.httpclient.HTTPClientError as e:
            if e.code == 599:
                # Gateway Timeout
                self.pp_gateway_timeout(project, service_name, address)
            elif hasattr(e, 'response') and e.response:
                # Generic HTTP error/redirect. Just forward
                self.proxy_handle_response(e.response)
            else:
                # Unknown error
                self.pp_502(project["name"], service_name, address)
                return
        except OSError as err:
            # No route to host / Name or service not known - Cache is probably too old
            return await self.retry_after_address_not_found_with_flushed_cache(project, service_name, err)

    def proxy_handle_response(self, response):
        self._headers = tornado.httputil.HTTPHeaders()  # clear tornado default header
        self.set_status(response.code, response.reason)

        for header, v in response.headers.get_all():
            if header not in ('Content-Length', 'Transfer-Encoding', 'Content-Encoding', 'Connection'):
                self.add_header(header, v)

        if response.body:
            self.set_header('Content-Length', len(response.body))
            self.set_header('X-Forwarded-By', 'riptide proxy')
            self.write(response.body)

    async def retry_after_address_not_found_with_flushed_cache(self, project, service_name, err):
        """ Retry the request again (once!) with cleared caches. """
        if self.request.__riptide_retried:
            self.pp_500(project["name"], service_name, err, traceback.format_exc())
            return
        self.request.__riptide_retried = True

        self.runtime_storage.projects_mapping = load_projects()
        self.runtime_storage.project_cache = {}
        self.runtime_storage.ip_cache = {}

        return await self.get()

    def pp_landing_page(self):
        """ TODO """
        self.set_status(200)
        self.render("pp_landing_page.html", title="Riptide Proxy", base_url=self.config["url"],
                    all_projects=get_all_projects(self.runtime_storage, logger))

    def pp_500(self, project_name, request_service_name, err, trace):
        """ TODO """
        self.set_status(500)
        logger.exception(err)
        self.render("pp_500.html", title="Riptide Proxy - 500 Internal Server Error", trace=trace, err=err)

    def pp_502(self, project_name, request_service_name, err):
        """ TODO """
        self.set_status(502)
        self.render("pp_502.html", title="Riptide Proxy - 502 Bad Gateway", err=err)

    def pp_no_main_service(self, project):
        """ TODO """
        self.set_status(503)
        self.render("pp_no_main_service.html", title="Riptide Proxy - No Main Service", project=project, base_url=self.config["url"])

    def pp_service_not_found(self, project, request_service_name):
        """ TODO """
        self.set_status(400)
        self.render("pp_service_not_found.html", title="Riptide Proxy - Service Not Found", project=project, base_url=self.config["url"], service_name=request_service_name)

    def pp_start_project(self, project, resolved_service_name):
        """ TODO """
        self.set_status(200)
        self.render("pp_start_project.html", title="Riptide Proxy - Starting...", project=project, service_name=resolved_service_name)

    def pp_project_not_started(self, project, resolved_service_name):
        """ TODO """
        self.set_status(503)
        self.render("pp_project_not_started.html", title="Riptide Proxy - Service Not Started", project=project, base_url=self.config["url"], service_name=resolved_service_name)

    def pp_project_not_found(self, project_name):
        """ TODO """
        self.set_status(400)
        self.render("pp_project_not_found.html", title="Riptide Proxy - Project Not Found",
                    project_name=project_name, base_url=self.config["url"],
                    all_projects=get_all_projects(self.runtime_storage, logger))

    def pp_gateway_timeout(self, project, service_name, address):
        """ TODO """
        self.set_status(504)
        self.render("pp_gateway_timeout.html", title="Riptide Proxy - Gateway Timeout", project=project, service_name=service_name)


class ProxyWebsocketHandler(websocket.WebSocketHandler):
    """ Implementation of the Proxy for Websockets """
    def __init__(self, application, request, config, engine, runtime_storage, **kwargs):
        """
        TODO
        :raises: FileNotFoundError if the system config was not found
        :raises: schema.SchemaError on validation errors
        """
        super().__init__(application, request, **kwargs)
        self.config = config
        self.engine = engine
        self.runtime_storage = runtime_storage
        self.conn = None

    async def open(self, *args, **kwargs):
        """
        Retreive the target container or close the connection with error if not found. After that act as Websocket Proxy.
        Source: https://github.com/tornadoweb/tornado/issues/2538
        """

        # TODO: CLEANUP DUPLICATE CODE

        project_name, request_service_name = extract_names_from(self.request, self.config["url"])
        if project_name is None:
            self.close(1014)  # 1014 is bad gateway
            return

        logger.debug("Incoming WebSocket Proxy request for project %s; service %s" % (project_name, request_service_name))

        try:
            project, resolved_service_name = resolve_project(project_name, request_service_name, self.runtime_storage, logger)

            if project:
                if not resolved_service_name:
                    if not request_service_name:
                        # Load main service if service_name not set
                        resolved_service_name = project["app"].get_service_by_role("main")["$name"]
                        if not resolved_service_name:
                            logger.warning("WebSocket Proxy: No main service for %s, %s" % (project_name, request_service_name))
                            self.close(1014)
                            return
                    else:
                        logger.warning("WebSocket Proxy: Service not found for %s, %s" % (project_name, request_service_name))
                        self.close(1014)
                        return
                # Resolve address and proxy the request
                address = resolve_container_address(project, resolved_service_name, self.engine, self.runtime_storage, logger)
                if not address:
                    logger.warning("WebSocket Proxy: Had no ip for %s, %s" % (project_name, request_service_name))
                    self.close(1014)
                    return
        except Exception as err:
            logger.warning("Errror during WebSocket proxy for %s, %s: %s"
                           % (project_name, request_service_name, str(err)))
            self.close(1014)
            return


        self.conn = await websocket_connect(address.replace('http://', 'ws://') + self.request.uri)

        async def proxy_loop():
            while True:
                msg = await self.conn.read_message()
                if msg is None:
                    break
                await self.write_message(msg)

        ioloop.IOLoop.current().spawn_callback(proxy_loop)
        logger.debug("Proxy established")

    def on_message(self, message):
        self.conn.write_message(message)

    def on_close(self, code=None, reason=None):
        self.conn.close(code, reason)


def run_proxy(system_config, engine, http_port, https_port, ssl_options, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    TODO
    """
    storage = {
        "config": system_config["proxy"],
        "engine": engine,
        "runtime_storage": RuntimeStorage(projects_mapping=load_projects(), project_cache={}, ip_cache={})
    }

    app = tornado.web.Application([
        (RiptideNoWebSocketMatcher(r'^(?!/___riptide_proxy_ws).*$'),    ProxyHandler,   storage),
        (r'^(?!/___riptide_proxy_ws).*$', ProxyWebsocketHandler, storage),
        (r'/___riptide_proxy_ws', AutostartHandler, storage),
    ], template_path=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'tpl'))
    # xheaders enables parsing of X-Forwarded-Ip etc. headers
    app.listen(http_port, xheaders=True)

    if https_port:
        https_app = tornado.httpserver.HTTPServer(app, ssl_options=ssl_options, xheaders=True)
        https_app.listen(https_port)

    ioloop = tornado.ioloop.IOLoop.current()
    if start_ioloop:
        ioloop.start()
