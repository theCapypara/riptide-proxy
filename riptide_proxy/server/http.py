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

import logging
from asyncio import Future, CancelledError

import tornado.httpclient
import tornado.httputil
import tornado.web
import traceback

from riptide.config.document.project import Project
from riptide.config.loader import load_projects
from riptide_proxy.project_loader import get_all_projects, resolve_project, ResolveStatus, ProjectLoadError
from riptide_proxy import UPSTREAM_REQUEST_TIMEOUT, UPSTREAM_CONNECT_TIMEOUT, LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


class ProxyHttpHandler(tornado.web.RequestHandler):

    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS")

    def __init__(self, application, request, config, engine, runtime_storage, **kwargs):
        """
        HTTP proxy handler. Handles incoming HTTP proxy requests, and sends them to the service containers
        (if possible), displays status pages otherwise.

        :raises: FileNotFoundError if the system config was not found
        :raises: schema.SchemaError on validation errors
        """
        super().__init__(application, request, **kwargs)
        self.config = config
        self.engine = engine
        self.runtime_storage = runtime_storage

        self.http_client = tornado.httpclient.AsyncHTTPClient()
        self.running_upstream_request_future: Future = None

        # Request id, only for debugging
        self.request_id = 0
        if logger.getEffectiveLevel() <= logging.DEBUG:
            import random, sys
            self.request_id = random.randint(0, sys.maxsize * 2 + 1)

    def compute_etag(self):
        return None  # disable tornado Etag

    def initialize(self):
        self.request.__riptide_retried = False

    async def get(self):
        """
        Route a reuqest to a service container or display status pages
        :return:
        """

        try:

            rc, data = resolve_project(self.request.host, self.config["url"],
                                       self.runtime_storage, self.config['autostart'])

            if rc == ResolveStatus.SUCCESS:
                project, resolved_service_name, address = data
                await self.reverse_proxy(project, resolved_service_name, address)
                return

            elif rc == ResolveStatus.NO_MAIN_SERVICE:
                project, request_service_name = data
                return self.pp_no_main_service(project)

            elif rc == ResolveStatus.SERVICE_NOT_FOUND:
                project, request_service_name = data
                return self.pp_service_not_found(project, request_service_name)

            elif rc == ResolveStatus.NOT_STARTED:
                project, resolved_service_name = data
                return self.pp_project_not_started(project, resolved_service_name)

            elif rc == ResolveStatus.NOT_STARTED_AUTOSTART:
                project, resolved_service_name = data
                return self.pp_start_project(project, resolved_service_name)

            elif rc == ResolveStatus.PROJECT_NOT_FOUND:
                project_name = data
                return self.pp_project_not_found(project_name)

            else:  # rc == ResolveStatus.NO_PROJECT
                return self.pp_landing_page()

        except ProjectLoadError as err:
            # Project could not be loaded
            self.pp_500_project_load(err)
        except Exception as err:
            # Unknown error happened, tell the user.
            self.pp_500(err, traceback.format_exc())
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

    def on_connection_close(self):
        """
        The connection was closed, before we finished processing. Close any running http clients (we don't
        need to wait for requests to finish if we don't have a user listening to the response.
        """
        logger.debug('[R %d] connection was closed by client. Aborting.', self.request_id)
        try:
            if self.running_upstream_request_future is not None:
                self.running_upstream_request_future.cancel()
                logger.debug('[R %d] successfully canceled upstream request future.', self.request_id)
            self.http_client.close()
            logger.debug('[R %d] successfully closed upstream connection.', self.request_id)
        except RuntimeError as ex:
            logger.debug('[R %d] upstream connection was already closed (%s).', self.request_id, str(ex))

    async def reverse_proxy(self, project: Project, service_name: str, address: str):
        """
        Reverse-proxy the to a given address

        :param project:         Project that the address belongs to
        :param service_name:    Service (name) in that project that the address belongs to
        :param address:         The address to the container, incl. port
        :return:
        """
        logger.debug('[R %d] Handle %s request to %s (%s)', self.request_id, self.request.method, project["name"], address)

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
                connect_timeout=UPSTREAM_CONNECT_TIMEOUT,
                request_timeout=UPSTREAM_REQUEST_TIMEOUT,
                allow_nonstandard_methods=True
            )
            self.running_upstream_request_future = self.http_client.fetch(req)
            response = await self.running_upstream_request_future
            # Close the connection. There seems to be an issue, where sometimes connections are not properly closed?
            self.http_client.close()
            logger.debug('[R %d] done.', self.request_id)
            # Handle the response
            self.proxy_handle_response(response)

        except tornado.httpclient.HTTPClientError as e:
            if e.code == 599:
                logger.debug('[R %d] error timeout.', self.request_id)
                # Gateway Timeout
                self.pp_gateway_timeout(project, service_name, address)
            elif hasattr(e, 'response') and e.response:
                logger.debug('[R %d] error generic.', self.request_id)
                # Generic HTTP error/redirect. Just forward
                self.proxy_handle_response(e.response)
            else:
                logger.debug('[R %d] error bad gateway.', self.request_id)
                # Unknown error
                self.pp_502(address)
                return

        except OSError as err:
            # No route to host / Name or service not known - Cache is probably too old
            return await self.retry_after_address_not_found_with_flushed_cache(project, service_name, err)

        except CancelledError:
            # The upstream request was canceled. This should only happen if the user has closed the connection,
            # but in case they haven't, send a nginx-like 499 Client Closed Request.
            self.set_status(499, "Client Closed Request")

    def proxy_handle_response(self, response: tornado.httpclient.HTTPResponse):
        """
        Handle a response from an upstream server (display it).

        :param response: The upstream response
        """

        self._headers = tornado.httputil.HTTPHeaders()  # clear tornado default header
        self.set_status(response.code, response.reason)

        for header, v in response.headers.get_all():
            # Some headers are not useful to send or have to be re-calculated.
            if header not in ('Content-Length', 'Transfer-Encoding', 'Content-Encoding', 'Connection'):
                self.add_header(header, v)

        if response.body:
            self.set_header('Content-Length', len(response.body))
            self.set_header('X-Forwarded-By', 'riptide proxy')
            self.write(response.body)

    async def retry_after_address_not_found_with_flushed_cache(self, project, service_name, err):
        """ Retry the request again (once!) with cleared caches. """
        if self.request.__riptide_retried:
            self.pp_500(err, traceback.format_exc())
            return
        self.request.__riptide_retried = True

        self.runtime_storage.projects_mapping = load_projects()
        self.runtime_storage.project_cache = {}
        self.runtime_storage.ip_cache = {}

        return await self.get()

    def pp_landing_page(self):
        """ Display the landing page """
        self.set_status(200)
        all_projects, load_errors = get_all_projects(self.runtime_storage)
        self.render("pp_landing_page.html", title="Riptide Proxy", base_url=self.config["url"],
                    all_projects=all_projects, load_errors=[self.format_load_error(error) for error in load_errors])

    def pp_500(self, err, trace, log_exception=True):
        """ Display a generic error page """
        self.set_status(500)
        if log_exception:
            logger.exception(err)
        self.render("pp_500.html", title="Riptide Proxy - 500 Internal Server Error", trace=trace, err=err, base_url=self.config["url"])

    def pp_500_project_load(self, err):
        """ Display project load error page """
        self.set_status(500)
        logger.error(str(err))
        self.render("pp_500_project_load.html", title="Riptide Proxy - Error loading project", trace=self.format_load_error(err), project=err.project_name, base_url=self.config["url"])

    def pp_502(self, err):
        """ Display a Bad Gateway error, if the upstream server sent an invalid response """
        self.set_status(502)
        self.render("pp_502.html", title="Riptide Proxy - 502 Bad Gateway", err=err, base_url=self.config["url"])

    def pp_no_main_service(self, project: Project):
        """ Inform the user that the project has no main service, and list available services. """
        self.set_status(503)
        self.render("pp_no_main_service.html", title="Riptide Proxy - No Main Service", project=project, base_url=self.config["url"])

    def pp_service_not_found(self, project: Project, request_service_name):
        """ Inform the user that a service was not found for the project, and list available services. """
        self.set_status(400)
        self.render("pp_service_not_found.html", title="Riptide Proxy - Service Not Found", project=project, base_url=self.config["url"], service_name=request_service_name)

    def pp_start_project(self, project: Project, resolved_service_name):
        """ Start the auto start procedure for a project """
        self.set_status(200)
        # Either start all or the defined default services
        if "default_services" in project:
            services_to_start = project["default_services"]
        else:
            services_to_start = project["app"]["services"].keys()
        # If the resolved service name is not in the list of services to start, show the start error page instead,
        # TODO: Extend autostart for this
        if resolved_service_name not in services_to_start:
            return self.pp_project_not_started(project, resolved_service_name)
        self.render("pp_start_project.html", title="Riptide Proxy - Starting...", services_to_start=services_to_start,
                    project=project, service_name=resolved_service_name, base_url=self.config["url"]
                    )

    def pp_project_not_started(self, project: Project, resolved_service_name):
        """ Inform the user, that the requested service is not started. """
        self.set_status(503)
        self.render("pp_project_not_started.html", title="Riptide Proxy - Service Not Started", project=project, base_url=self.config["url"], service_name=resolved_service_name)

    def pp_project_not_found(self, project_name):
        """ Inform the user, that the requested project was not found, and display a list of all projects. """
        self.set_status(400)
        self.render("pp_project_not_found.html", title="Riptide Proxy - Project Not Found",
                    project_name=project_name, base_url=self.config["url"])

    def pp_gateway_timeout(self, project, service_name, address):
        """ Inform the user of a Gateway Timeout and possible reasons for this. """
        self.set_status(504)
        self.render("pp_gateway_timeout.html", title="Riptide Proxy - Gateway Timeout", project=project, service_name=service_name, base_url=self.config["url"])

    def format_load_error(self, err: ProjectLoadError):
        """ Formats ProjectLoadErrors for display """
        stack = [str(err)]
        current_err = err
        previous_message = str(err)
        while current_err.__context__ is not None:
            current_err = current_err.__context__
            # Filter duplicate exception messages. 'schema' used by configcrunch does that for example.
            if previous_message != str(current_err):
                stack.append(f'>> Caused by {str(current_err)}')
            previous_message = str(current_err)
        return stack
