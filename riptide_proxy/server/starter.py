import logging
import tornado.httpserver
import tornado.ioloop
import tornado.routing
import tornado.web
from importlib.util import find_spec

from riptide.config.document.config import Config
from riptide.config.loader import load_projects
from riptide.engine.abstract import AbstractEngine
from riptide.plugin.loader import load_plugins
from riptide_proxy import LOGGER_NAME
from riptide_proxy.abstract_plugin import ProxyServerPlugin
from riptide_proxy.project_loader import RuntimeStorage
from riptide_proxy.resources import get_resources
from riptide_proxy.server.http import ProxyHttpHandler
from riptide_proxy.server.websocket.others import ProxyWebsocketHandler
from riptide_proxy.server.websocket.autostart import AutostartHandler

logger = logging.getLogger(LOGGER_NAME)
RIPTIDE_MISSION_CONTROL_SUBDOMAIN = "control"
RIPTIDE_PROFILING_SUBDOMAIN = "sys--dbg--profile"


def load_plugin_routes(system_config: Config, engine: AbstractEngine, https_port, storage: RuntimeStorage):
    routes = []

    # Riptide Plugin routes
    for plugin in load_plugins().values():
        if isinstance(plugin, ProxyServerPlugin):
            routes += plugin.get_routes(system_config, storage)

    # Riptide Mission Control
    mc_spec = find_spec("riptide_mission_control")
    if mc_spec is not None:
        from riptide_mission_control.server.starter import get_for_external

        start_https_msg = ""

        if https_port:
            start_https_msg = f"\n    https://{RIPTIDE_MISSION_CONTROL_SUBDOMAIN}.{system_config['proxy']['url']}:{system_config['proxy']['ports']['https']:d}"

        logger.info(
            f"Riptide Mission Control is also started at:\n"
            f"    http://{RIPTIDE_MISSION_CONTROL_SUBDOMAIN}.{system_config['proxy']['url']}:{system_config['proxy']['ports']['http']:d}{start_https_msg}"
        )
        routes += get_for_external(
            system_config, engine, f"{RIPTIDE_MISSION_CONTROL_SUBDOMAIN}.{system_config['proxy']['url']}"
        )
    # Profiling
    guppy_spec = find_spec("guppy")
    if guppy_spec is not None:
        from riptide_proxy.profiling import get_profiling_route

        start_https_msg = ""
        if https_port:
            start_https_msg = f"\n    https://{RIPTIDE_PROFILING_SUBDOMAIN}.{system_config['proxy']['url']}:{system_config['proxy']['ports']['https']:d}"

        logger.info(
            f"Profiling extension guppy installed. Available at:\n"
            f"    http://{RIPTIDE_PROFILING_SUBDOMAIN}.{system_config['proxy']['url']}:{system_config['proxy']['ports']['http']:d}{start_https_msg}"
        )

        routes += get_profiling_route(f"{RIPTIDE_PROFILING_SUBDOMAIN}.{system_config['proxy']['url']}")
    return routes


def run_proxy(system_config: Config, engine: AbstractEngine, http_port, https_port, ssl_options, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    """

    start_https_msg = ""

    if https_port:
        start_https_msg = f"\n    https://{system_config['proxy']['url']}:{system_config['proxy']['ports']['https']:d}"

    logger.info(
        f"Starting Riptide Proxy at: \n"
        f"    http://{system_config['proxy']['url']}:{system_config['proxy']['ports']['http']:d}{start_https_msg}"
    )

    # Load projects initially
    projects = load_projects()

    # Configure global storage
    use_compression = (
        True if "compression" in system_config["proxy"] and system_config["proxy"]["compression"] else False
    )
    storage = {
        "config": system_config["proxy"],
        "engine": engine,
        "runtime_storage": RuntimeStorage(
            projects_mapping=projects, project_cache={}, ip_cache={}, engine=engine, use_compression=use_compression
        ),
    }

    # Configure Routes
    app = tornado.web.Application(
        load_plugin_routes(system_config, engine, https_port, storage["runtime_storage"])
        + [
            # http
            (RiptideNoWebSocketMatcher(r"^(?!/___riptide_proxy_ws).*$"), ProxyHttpHandler, storage),
            # Any non-autostart websockets
            (r"^(?!/___riptide_proxy_ws).*$", ProxyWebsocketHandler, storage),
            # autostart websockets
            (r"/___riptide_proxy_ws", AutostartHandler, storage),
        ],
        template_path=get_resources(),
    )

    # xheaders enables parsing of X-Forwarded-Ip etc. headers
    app.listen(http_port, xheaders=True)

    # Prepare HTTPS
    if https_port:
        https_app = tornado.httpserver.HTTPServer(app, ssl_options=ssl_options, xheaders=True)
        https_app.listen(https_port)

    # Start!
    ioloop = tornado.ioloop.IOLoop.current()
    if start_ioloop:
        ioloop.start()


class RiptideNoWebSocketMatcher(tornado.routing.PathMatches):
    def match(self, request):
        """Match path but ONLY non-Websocket requests"""
        if "Upgrade" in request.headers and request.headers["Upgrade"] == "websocket":
            return None
        return super().match(request)
