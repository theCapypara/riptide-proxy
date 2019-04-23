"""template file management"""
import pkg_resources


def get_resources():
    return pkg_resources.resource_filename(__name__, 'tpl')
