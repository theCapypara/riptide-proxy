"""template file management"""

import atexit
import importlib.resources

from contextlib import ExitStack


def get_resources(kind: str):
    file_manager = ExitStack()
    atexit.register(file_manager.close)
    package_name = __name__.split(".")[0]
    ref = importlib.resources.files(package_name) / kind
    path = file_manager.enter_context(importlib.resources.as_file(ref))
    return path
