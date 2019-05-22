import logging
import pkg_resources
import tornado.httpserver
import tornado.ioloop
import tornado.routing
import tornado.web

from riptide.config.loader import load_projects
from riptide_proxy import LOGGER_NAME
from riptide_proxy.project_loader import RuntimeStorage
from riptide_proxy.resources import get_resources
from riptide_proxy.server.http import ProxyHttpHandler
from riptide_proxy.server.websocket.others import ProxyWebsocketHandler
from riptide_proxy.server.websocket.autostart import AutostartHandler

logger = logging.getLogger(LOGGER_NAME)


def run_proxy(system_config, engine, http_port, https_port, ssl_options, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    """

    logger.info("Starting Riptide Proxy on HTTP: http://%s:%d"
                % (system_config["proxy"]["url"], system_config["proxy"]["ports"]["http"]))

    # Load projects initially
    projects = load_projects()

    # Configure global storage
    storage = {
        "config": system_config["proxy"],
        "engine": engine,
        "runtime_storage": RuntimeStorage(projects_mapping=projects, project_cache={}, ip_cache={})
    }

    # Configure Routes
    app = tornado.web.Application([
        # http
        (RiptideNoWebSocketMatcher(r'^(?!/___riptide_proxy_ws).*$'), ProxyHttpHandler, storage),
        # Any non-autostart websockets
        (r'^(?!/___riptide_proxy_ws).*$', ProxyWebsocketHandler, storage),
        # autostart websockets
        (r'/___riptide_proxy_ws', AutostartHandler, storage),
    ], template_path=get_resources())

    # xheaders enables parsing of X-Forwarded-Ip etc. headers
    app.listen(http_port, xheaders=True)

    # Prepare HTTPS
    if https_port:
        logger.info("Starting Riptide Proxy on HTTPS: https://%s:%d"
                    % (system_config["proxy"]["url"], system_config["proxy"]["ports"]["https"]))
        https_app = tornado.httpserver.HTTPServer(app, ssl_options=ssl_options, xheaders=True)
        https_app.listen(https_port)

    # Start!
    ioloop = tornado.ioloop.IOLoop.current()
    if start_ioloop:
        ioloop.start()


class RiptideNoWebSocketMatcher(tornado.routing.PathMatches):
    def match(self, request):
        """ Match path but ONLY non-Websocket requests """
        if "Upgrade" in request.headers and request.headers["Upgrade"] == "websocket":
            return None
        return super().match(request)
