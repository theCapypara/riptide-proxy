"""Checks auto-start related restrictions (whether a client is allowed to start projects via the server or not)"""
import ipaddress
import logging

from riptide.config.document.config import Config
from riptide_proxy import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def check_permission(ipv4address: str, config) -> bool:
    if 'autostart_restrict' not in config:
        return True
    try:
        ipv4address_network = ipaddress.ip_network(f'{ipv4address}/32')
    except ValueError as err:
        logger.warning(f"Invalid IPv4 addresss for client: {ipv4address}: {err}")

    for network_str in config['autostart_restrict']:
        try:
            network = ipaddress.ip_network(network_str)
            if network.overlaps(ipv4address_network):
                return True
        except ValueError as err:
            logger.warning(f"Invalid IPv4 network in system config autostart_restrict: {network_str}: {err}")
    return False
