from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from riptide.config.document.config import Config
    from riptide.config.document.project import Project
    from riptide.engine.abstract import AbstractEngine
from riptide_proxy import LOGGER_NAME
from riptide_proxy.project_loader import ResolveStatus, RuntimeStorage, resolve_project
from riptide_proxy.server.websocket import ERR_BAD_GATEWAY
from tornado import httpclient, ioloop, websocket
from tornado.websocket import WebSocketClientConnection, websocket_connect

logger = logging.getLogger(LOGGER_NAME)


class ProxyWebsocketHandler(websocket.WebSocketHandler):
    """Implementation of the Proxy for Websockets"""

    def __init__(
        self, application, request, config: Config, engine: AbstractEngine, runtime_storage: RuntimeStorage, **kwargs
    ):
        """
        :raises: FileNotFoundError if the system config was not found
        :raises: schema.SchemaError on validation errors
        """
        super().__init__(application, request, **kwargs)
        self.config: Config = config
        self.engine: AbstractEngine = engine
        self.runtime_storage: RuntimeStorage = runtime_storage
        self.conn: WebSocketClientConnection | None = None
        self.project: Project | None = None

    async def open(self, *args, **kwargs):
        """
        Retreive the target container or close the connection with error if not found. After that act as Websocket Proxy.

        Source: https://github.com/tornadoweb/tornado/issues/2538
        """

        try:
            logger.debug(f"Incoming WebSocket Proxy request for {self.request.host}")

            rc, data = resolve_project(
                self.request.host, self.config["url"], self.runtime_storage, self.config["autostart"]
            )

            if rc == ResolveStatus.NO_MAIN_SERVICE:
                project, request_service_name = data
                logger.warning(f"WebSocket Proxy: No main service for {project['name']}, {request_service_name}")
                self.close(ERR_BAD_GATEWAY)
                return

            elif rc == ResolveStatus.SERVICE_NOT_FOUND:
                project, request_service_name = data
                logger.warning(f"WebSocket Proxy: Service not found for {project['name']}, {request_service_name}")
                self.close(ERR_BAD_GATEWAY)
                return

            elif rc == ResolveStatus.NOT_STARTED or rc == ResolveStatus.NOT_STARTED_AUTOSTART:
                project, resolved_service_name = data
                logger.warning(
                    f"WebSocket Proxy: Had no ip for {project['name']}, {resolved_service_name}. Not started?"
                )
                self.close(ERR_BAD_GATEWAY)
                return

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

        self.project = project

        # Establish reverse proxy connection with upstream server
        backend_request = httpclient.HTTPRequest(
            url=address.replace("http://", "ws://") + self.request.uri,
            headers=self.request.headers,
            method=self.request.method or "GET",
        )
        self.conn = await websocket_connect(backend_request)

        async def proxy_loop():
            assert self.conn is not None
            assert self.project is not None
            while True:
                msg = await self.conn.read_message()
                logger.debug(f"WebSocket Proxy ({self.project['name']}): received msg (server)")
                if msg is None:
                    break
                await self.write_message(msg, binary=isinstance(msg, bytes))
                logger.debug(f"WebSocket Proxy ({self.project['name']}): write msg (client)")

        # Start backend read/write loop
        ioloop.IOLoop.current().spawn_callback(proxy_loop)
        logger.debug(f"WebSocket Proxy ({self.project['name']}): reverse proxy established")

    def select_subprotocol(self, subprotocols):
        if len(subprotocols) == 0:
            return None
        return subprotocols[0]

    def on_message(self, message):
        # Send message to backend
        assert self.conn is not None
        assert self.project is not None
        logger.debug(f"WebSocket Proxy ({self.project['name']}): received msg (client)")
        self.conn.write_message(message, binary=isinstance(message, bytes))
        logger.debug(f"WebSocket Proxy ({self.project['name']}): write msg (server)")

    def on_close(self, code=None, reason=None):
        # Close backend connection
        assert self.project is not None
        logger.debug(f"WebSocket Proxy ({self.project['name']}): closed (client)")
        if self.conn is not None:
            self.conn.close(code, reason)
        logger.debug(f"WebSocket Proxy ({self.project['name']}): closed (server)")
