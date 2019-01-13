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
# TODO Testing:
# - https://github.com/mnot/cdn-tests

import logging
import os
import socket
import time
from typing import Tuple, Union, Dict

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient
import tornado.httputil
import traceback
from recordclass import RecordClass

from riptide.config.document.project import Project
from riptide.config.document.service import Service
from riptide.config.loader import load_projects, load_config

logger = logging.getLogger('tornado_proxy')
# TODO: Autostop
# TODO: SSL

logger.setLevel(logging.DEBUG)


class RuntimeStorage(RecordClass):
    projects_mapping: Dict
    # A cache of projects. Contains a mapping (project file path) => [project object, age]
    project_cache: Dict
    # A cache of ip addresses for services. Contains a mapping (project_name + "__" + service_name) => [address, age]
    ip_cache: Dict


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

        riptide_host_part = "".join(self.request.host.rsplit("." + self.config["url"]))
        logger.debug('Incoming request for %s', riptide_host_part)
        if riptide_host_part == self.config["url"]:
            self.pp_landing_page()
            return

        parts = riptide_host_part.split("__")
        project_name = parts[0]
        request_service_name = None
        if len(parts) > 1:
            request_service_name = "__".join(parts[1:])

        try:
            project, resolved_service_name = self.resolve_project(project_name, request_service_name)

            if project:
                if not resolved_service_name:
                    if not request_service_name:
                        # Load main service if service_name not set
                        resolved_service_name = project["app"].get_service_name_by_role("main")
                        if not resolved_service_name:
                            self.pp_no_main_service(project)
                            return
                    else:
                        self.pp_service_not_found(project, request_service_name)
                        return
                # Resolve address and proxy the request
                address = self.resolve_container_address(project, resolved_service_name)
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
                headers=self.request.headers,
                follow_redirects=False,
                connect_timeout=20,  # todo configurable
                request_timeout=6000,  # todo configurable
                decompress_response=False
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

    def resolve_project(self, project_name, service_name) -> Tuple[Union[Project, None], Union[Service, None]]:
        """
        Resolves the project object and service name for the project identified by hostname
        Service name may be None if no service was specified, and project is None if no project could be loaded.
        """

        # Get project file
        if project_name not in self.runtime_storage.projects_mapping:
            # Try to reload. Maybe it was added?
            self.runtime_storage.projects_mapping = load_projects()
            if project_name not in self.runtime_storage.projects_mapping:
                logger.debug('Could not find project %s' % project_name)
                # Project not found
                return None, None

        # Load project from cache. Cache times out after some time.
        cache_timeout = 120  ## TODO CONFIGURABLE
        current_time = time.time()
        project_file = self.runtime_storage.projects_mapping[project_name]
        project_cache = self.runtime_storage.project_cache
        if project_file not in project_cache or current_time - project_cache[project_file][1] > cache_timeout:
            logger.debug('Loading project file for %s at %s' % (project_name, project_file))
            project = load_config(project_file)["project"]
            project_cache[project_file] = [project, current_time]
        else:
            project = project_cache[project_file][0]
            project_cache[project_file][1] = current_time

        # Resolve service - simply return the service name again if found, otherwise just the project
        if service_name in project["app"]["services"]:
            return project, service_name
        return project, None

    def resolve_container_address(self, project, service_name):
        cache_timeout = 120  ## TODO CONFIGURABLE
        key = project["name"] + "__" + service_name
        current_time = time.time()
        ip_cache = self.runtime_storage.ip_cache
        if key not in ip_cache or current_time - ip_cache[key][1] > cache_timeout:
            address = self.engine.address_for(project, service_name)
            logger.debug('Got container address for %s: %s' % (key, address))
            if address:
                address = "http://" + address[0] + ":" + str(address[1])
                # Only cache if we actually got something.
                ip_cache[key] = [address, current_time]
        else:
            address = ip_cache[key][0]
            ip_cache[key][1] = current_time
        return address

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
        self.render("pp_landing_page.html", title="Riptide Proxy")

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
        self.render("pp_project_not_found.html", title="Riptide Proxy - Project Not Found", project_name=project_name)

    def pp_gateway_timeout(self, project, service_name, address):
        """ TODO """
        # TODO Link with Reset.
        self.set_status(504)
        self.render("pp_gateway_timeout.html", title="Riptide Proxy - Gateway Timeout", project=project, service_name=service_name)


def run_proxy(port, system_config, engine, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    TODO
    """
    runtime_storage = RuntimeStorage(projects_mapping=load_projects(), project_cache={}, ip_cache={})
    app = tornado.web.Application([
        (r'.*', ProxyHandler, {
            "config": system_config["proxy"],
            "engine": engine,
            "runtime_storage": runtime_storage
        }),
    ], template_path=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'tpl'))
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.current()
    if start_ioloop:
        ioloop.start()
