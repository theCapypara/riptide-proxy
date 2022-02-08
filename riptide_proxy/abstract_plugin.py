from abc import ABC, abstractmethod

from riptide.config.document.config import Config
from riptide_proxy.project_loader import RuntimeStorage


class ProxyServerPlugin(ABC):
    """
    A Riptide plugin that (also) extends the functionality of the proxy server.

    For this it can:

    - Add new routes to the proxy server that get checked before any of the integrated routes.
    """

    @abstractmethod
    def get_routes(self, config: Config, runtime_storage: RuntimeStorage):
        """Returns a list of handlers for Tornado. See documentation of tornado.web.Application for documentation."""
