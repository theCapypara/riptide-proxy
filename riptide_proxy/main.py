import click
from click import echo

from riptide.cli.helpers import RiptideCliError
from riptide.config.document.config import Config
from riptide.config.loader import load_engine
from riptide.config.files import riptide_main_config_file
from riptide_proxy.server import run_proxy


@click.command()
@click.pass_context
def main(ctx):
    """
    TODO Description and arguments/options
    """
    port = 8888
    # todo configurable
    try:
        config_path = riptide_main_config_file()
        system_config = Config.from_yaml(config_path)
        system_config.validate()
    except FileNotFoundError as e:
        raise RiptideCliError("Main config file not found. Run riptide config:create:user.", ctx) from e
    except Exception as e:
        raise RiptideCliError("Error reading configuration.", ctx) from e

    try:
        engine = load_engine(system_config["engine"])
    except NotImplementedError as ex:
        raise RiptideCliError('Unknown engine specified in configuration.', ctx) from ex

    echo("Starting HTTP proxy on port %d" % port)

    run_proxy(port, system_config, engine)

# tornado doku: http://www.tornadoweb.org/en/stable/guide/structure.html
# tornado rp base: https://github.com/senko/tornado-proxy/blob/master/tornado_proxy/proxy.py
# websockets doku: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications
