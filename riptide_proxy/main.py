import os

import click
from click import echo, ClickException, style
from tempfile import TemporaryDirectory

from riptide.config.document.config import Config
from riptide.config.files import riptide_main_config_file
from riptide.engine.loader import load_engine
from riptide_proxy.privileges import drop_privileges
from riptide_proxy.server import run_proxy
from riptide_proxy.ssl_key import *


@click.command()
@click.option('--user', '-u', default=os.environ.get('SUDO_USER'),
              help='Only on POSIX systems when running as root: '
                   'Specify user configuration to use. Ignored otherwise. '
                   'Defaults to environment variable SUDO_USER')
def main(user):
    """
    TODO Description and arguments/options
    """

    # Set privileges and drop back to user level
    try:
        if os.getuid() == 0:
            if not user:
                raise ClickException("--user parameter required when running as root.")
            echo("Was running as root. Changing user to %s." % user)
            drop_privileges(user)
    except AttributeError:
        # Windows. Ignore.
        pass

    # Read system config
    try:
        config_path = riptide_main_config_file()
        system_config = Config.from_yaml(config_path)
        system_config.validate()
    except FileNotFoundError as e:
        raise ClickException("Main config file not found. Run riptide config:create:user.") from e
    except Exception as e:
        raise ClickException("Error reading configuration.") from e

    # Read engine
    try:
        engine = load_engine(system_config["engine"])
    except NotImplementedError as ex:
        raise ClickException('Unknown engine specified in configuration.') from ex

    # load SSL
    with TemporaryDirectory() as temp_dir:
        ssl_options = None
        if system_config["proxy"]["ports"]["https"]:
            pem_file = create_keys(temp_dir, system_config["proxy"]["url"])
            echo("Starting Riptide Proxy on HTTPS port %d" % system_config["proxy"]["ports"]["https"])
            ssl_options = {
                "certfile": pem_file,
                "keyfile": pem_file,
            }

        echo("Starting Riptide Proxy on HTTP port %d" % system_config["proxy"]["ports"]["http"])

        # Run Proxy
        run_proxy(
            system_config,
            engine,
            http_port=system_config["proxy"]["ports"]["http"],
            https_port=system_config["proxy"]["ports"]["https"],
            ssl_options=ssl_options
        )

# tornado doku: http://www.tornadoweb.org/en/stable/guide/structure.html
# tornado rp base: https://github.com/senko/tornado-proxy/blob/master/tornado_proxy/proxy.py
# websockets doku: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications
