import os

import click
from click import echo, ClickException

from riptide.config.document.config import Config
from riptide.config.files import riptide_main_config_file
from riptide.engine.loader import load_engine
from riptide_proxy.privileges import drop_privileges
from riptide_proxy.server import run_proxy


@click.command()
@click.option('--user', '-u', default=os.environ.get('SUDO_USER'),
              help='Only on POSIX systems when running as root: '
                   'Specify user configuration to use. Ignored otherwise. '
                   'Defaults to environment variable SUDO_USER')
@click.pass_context
def main(ctx, user):
    """
    TODO Description and arguments/options
    """
    try:
        if os.getuid() == 0:
            if not user:
                raise ClickException("--user parameter required when running as root.")
            echo("Was running as root. Changing user to %s." % user)
            drop_privileges(user)
    except AttributeError:
        # Windows. Ignore.
        pass

    try:
        config_path = riptide_main_config_file()
        system_config = Config.from_yaml(config_path)
        system_config.validate()
    except FileNotFoundError as e:
        raise ClickException("Main config file not found. Run riptide config:create:user.", ctx) from e
    except Exception as e:
        raise ClickException("Error reading configuration.", ctx) from e

    try:
        engine = load_engine(system_config["engine"])
    except NotImplementedError as ex:
        raise ClickException('Unknown engine specified in configuration.', ctx) from ex

    echo("Starting Riptide Proxy on port %d" % system_config["proxy"]["ports"]["http"])

    run_proxy(system_config["proxy"]["ports"]["http"], system_config, engine)

# tornado doku: http://www.tornadoweb.org/en/stable/guide/structure.html
# tornado rp base: https://github.com/senko/tornado-proxy/blob/master/tornado_proxy/proxy.py
# websockets doku: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications
