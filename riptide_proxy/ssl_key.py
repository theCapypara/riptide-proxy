import os
import socket
from certauth.certauth import CertificateAuthority

from riptide.config.files import riptide_config_dir

RIPTIDE_PROXY_CONFIG_DIR = 'riptide_proxy'
CA_NAME = 'ca.pem'


def get_config_dir():
    return os.path.join(riptide_config_dir(), RIPTIDE_PROXY_CONFIG_DIR)


def get_ca_path():
    return os.path.join(get_config_dir(), CA_NAME)


def create_keys(temp_dir, common_name):
    ca = CertificateAuthority('Riptide Proxy CA for %s' % socket.gethostname(),
                              get_ca_path(), cert_cache=temp_dir)
    return ca.get_wildcard_cert('*.' + common_name)
