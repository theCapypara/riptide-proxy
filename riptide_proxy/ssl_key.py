"""This module manages HTTPS for the server"""
import logging
import os
import socket
from certauth.certauth import CertificateAuthority

from riptide.config.files import riptide_config_dir
from riptide_proxy import LOGGER_NAME

RIPTIDE_PROXY_CONFIG_DIR = 'riptide_proxy'
CA_NAME = 'ca.pem'

NOT_VALID_AFTER = 364 * 24 * 60 * 60

logger = logging.getLogger(LOGGER_NAME)


def get_config_dir():
    """Returns the proxy server configuration dir"""
    return os.path.join(riptide_config_dir(), RIPTIDE_PROXY_CONFIG_DIR)


def get_ca_path():
    """Returns the path to the SSL CA file"""
    return os.path.join(get_config_dir(), CA_NAME)


def create_keys(temp_dir, common_name):
    """Create wildcard certificate for the proxy base url."""
    ca = CertificateAuthority(f'Riptide Proxy CA for {socket.gethostname()}',
                              get_ca_path(), cert_cache=temp_dir,
                              # Make it valid for 364 days, as per MacOS Catalina requirements
                              cert_not_after=NOT_VALID_AFTER)

    if ca.ca_cert.has_expired():
        logger.warning("The CA certificate had to be re-generated because"
                       "it was no longer valid. You may need to re-import it,"
                       "please see the documentation.")
        ca = CertificateAuthority(f'Riptide Proxy CA for {socket.gethostname()}',
                              get_ca_path(), cert_cache=temp_dir,
                              cert_not_after=NOT_VALID_AFTER, overwrite=True)

    return ca.get_wildcard_cert('*.' + common_name)
