import logging
from tornado import websocket, ioloop
from tornado.websocket import websocket_connect

from riptide_proxy import LOGGER_NAME
from riptide_proxy.project_loader import resolve_project, ResolveStatus
from riptide_proxy.server.websocket import ERR_BAD_GATEWAY

logger = logging.getLogger(LOGGER_NAME)


class ProxyWebsocketHandler(websocket.WebSocketHandler):
    """ Implementation of the Proxy for Websockets """
    def __init__(self, application, request, config, engine, runtime_storage, **kwargs):
        """
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

        try:

            logger.debug(f"Incoming WebSocket Proxy request for {self.request.host}")

            rc, data = resolve_project(self.request.host, self.config["url"],
                                       self.engine, self.runtime_storage, self.config['autostart'])

            if rc == ResolveStatus.NO_MAIN_SERVICE:
                project, request_service_name = data
                logger.warning(f"WebSocket Proxy: No main service for {project['name']}, {request_service_name}")
                self.close(ERR_BAD_GATEWAY)

            elif rc == ResolveStatus.SERVICE_NOT_FOUND:
                project, request_service_name = data
                logger.warning(f"WebSocket Proxy: Service not found for {project['name']}, {request_service_name}")
                self.close(ERR_BAD_GATEWAY)

            elif rc == ResolveStatus.NOT_STARTED or rc == ResolveStatus.NOT_STARTED_AUTOSTART:
                project, resolved_service_name = data
                logger.warning(
                    f"WebSocket Proxy: Had no ip for {project['name']}, {resolved_service_name}. Not started?"
                )
                self.close(ERR_BAD_GATEWAY)

            elif rc == ResolveStatus.PROJECT_NOT_FOUND:
                project_name = data
                logger.warning(f"WebSocket Proxy: Project not found for {project_name}")
                self.close(ERR_BAD_GATEWAY)
                return

            elif rc == ResolveStatus.NO_PROJECT:
                self.close(ERR_BAD_GATEWAY)
                return

        except Exception as err:
            logger.warning(f"Errror during WebSocket proxy for {self.request.host}: {str(err)}.")
            self.close(ERR_BAD_GATEWAY)
            return

        if rc != ResolveStatus.SUCCESS:
            logger.warning(f"WebSocket Proxy: Unknown status: {rc:d}")
            self.close(ERR_BAD_GATEWAY)
            return

        project, resolved_service_name, address = data

        # Establish reverse proxy connection with upstream server
        self.conn = await websocket_connect(address.replace('http://', 'ws://') + self.request.uri)

        async def proxy_loop():
            while True:
                msg = await self.conn.read_message()
                if msg is None:
                    break
                await self.write_message(msg)

        # Start backend read/write loop
        ioloop.IOLoop.current().spawn_callback(proxy_loop)
        logger.debug("Websocket proxy established")

    def on_message(self, message):
        # Send message to backend
        self.conn.write_message(message)

    def on_close(self, code=None, reason=None):
        # Close backend connection
        self.conn.close(code, reason)
