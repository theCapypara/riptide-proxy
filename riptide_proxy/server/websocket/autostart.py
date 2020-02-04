import json
import logging
from tornado import websocket

from riptide_proxy import LOGGER_NAME
from riptide_proxy.project_loader import load_project_and_service
from riptide_proxy.server.websocket import ERR_BAD_GATEWAY

logger = logging.getLogger(LOGGER_NAME)


def try_write(client, msg):
    """Try to send a message over a Websocket and silently fail."""
    try:
        client.write_message(msg)
    except:
        pass


def build_status_answer(service_name, status, finished):
    """Build the autostart answer json based on event"""
    if finished:
        if status:
            update = {
                'service': service_name,
                'error': str(status)
            }
        else:
            # no error
            update = {
                'service': service_name,
                'finished': True
            }
            pass
    else:
        # update
        update = {
            'service': service_name,
            'status': {
                'steps': status.steps,
                'current_step': status.current_step,
                'text': status.text
            }
        }
        pass
    return {
        'status': 'update',
        'update': update
    }


class AutostartHandler(websocket.WebSocketHandler):

    def __init__(self, application, request, config, engine, runtime_storage, **kwargs):
        """
        Websocket connection for autostarting a service.
        """
        super().__init__(application, request, **kwargs)
        self.project = None
        self.config = config
        self.engine = engine
        self.runtime_storage = runtime_storage

    clients = {}

    # True if any of the WebSocket object coroutines currently starts the project
    running = False

    def check_origin(self, origin):
        return True

    def open(self):
        logger.debug(f'Autostart WS: Connection from {self.request.remote_ip}. Waiting for project name...')

    def on_close(self):
        if self.project:
            logger.debug('Autostart WS: Connection from {} for {} CLOSED'.format(self.request.remote_ip, self.project["name"]))

            # Remove from list of clients
            if self in self.__class__.clients:
                self.__class__.clients[self.project["name"]].remove(self)

    async def on_message(self, message):
        decoded_message = json.loads(message)

        # Register a project to monitor for this websocket connection
        if decoded_message['method'] == "register":  # {method: register, project: ...}
            project, _ = load_project_and_service(decoded_message['project'], None, self.runtime_storage)
            if project is None:
                self.close(ERR_BAD_GATEWAY, 'Project not found.')
                return

            self.project = project

            logger.debug('Autostart WS: Connection from {} for {}'.format(self.request.remote_ip, self.project["name"]))

            # Add to list of clients
            if self not in self.__class__.clients:
                if self.project["name"] not in self.__class__.clients:
                    self.__class__.clients[self.project["name"]] = []
                self.__class__.clients[self.project["name"]].append(self)

            self.write_message(json.dumps({'status': 'ready'}))

        # Start the registered project
        elif decoded_message['method'] == "start" and self.project:  # {method: start}
            p_name = self.project["name"]
            logger.debug(f'Autostart WS: Start Request for {p_name} from {self.request.remote_ip}')
            if not self.__class__.running:
                logger.debug('Autostart WS: STARTING project %s!', p_name)
                self.__class__.running = True
                had_an_error = False
                try:
                    # Either start all or the defined default services
                    if "default_services" in self.project:
                        services = self.project["default_services"]
                    else:
                        services = self.project["app"]["services"].keys()
                    async for service_name, status, finished in self.engine.start_project(self.project, services):
                        for client in self.__class__.clients[p_name]:
                            try_write(client, json.dumps(build_status_answer(service_name, status, finished)))
                        if status and finished:
                            had_an_error = True
                except Exception as err:
                    logger.warning('Autostart WS: Project %s start ERROR: %s', (p_name, str(err)))
                    for client in self.__class__.clients[p_name]:
                        try_write(client, json.dumps({'status': 'error', 'msg': str(err)}))
                else:
                    if not had_an_error:
                        # Finished
                        logger.debug('Autostart WS: Project %s STARTED!', p_name)
                        for client in self.__class__.clients[p_name]:
                            try_write(client, json.dumps({'status': 'success'}))
                    else:
                        logger.debug('Autostart WS: Project %s ERROR!', p_name)
                        for client in self.__class__.clients[p_name]:
                            try_write(client, json.dumps({'status': 'failed'}))
                self.__class__.running = False
