import time

from logging import Logger
from recordclass import RecordClass
from typing import Tuple, Union, Dict, List

from riptide.config.document.project import Project
from riptide.config.document.service import Service, DOMAIN_PROJECT_SERVICE_SEP
from riptide.config.loader import load_projects, load_config


class RuntimeStorage(RecordClass):
    projects_mapping: Dict
    # A cache of projects. Contains a mapping (project file path) => [project object, age]
    project_cache: Dict
    # A cache of ip addresses for services. Contains a mapping (project_name + "__" + service_name) => [address, age]
    ip_cache: Dict


def extract_names_from(request, base_url):
    # Remove ports from host
    real_host = request.host.split(":")[0]
    riptide_host_part = "".join(real_host.rsplit("." + base_url))
    if riptide_host_part == base_url:
        return None, None

    parts = riptide_host_part.split(DOMAIN_PROJECT_SERVICE_SEP)
    project_name = parts[0]
    request_service_name = None
    if len(parts) > 1:
        request_service_name = DOMAIN_PROJECT_SERVICE_SEP.join(parts[1:])

    return project_name, request_service_name


def resolve_project(project_name, service_name, runtime_storage: RuntimeStorage, logger: Logger) \
        -> Tuple[Union[Project, None], Union[Service, None]]:
    """
    Resolves the project object and service name for the project identified by hostname
    Service name may be None if no service was specified, and project is None if no project could be loaded.
    """

    # Get project file
    if project_name not in runtime_storage.projects_mapping:
        # Try to reload. Maybe it was added?
        runtime_storage.projects_mapping = load_projects()
        if project_name not in runtime_storage.projects_mapping:
            logger.debug('Could not find project %s' % project_name)
            # Project not found
            return None, None

    # Load project from cache. Cache times out after some time.
    cache_timeout = 120  ## TODO CONFIGURABLE
    current_time = time.time()
    project_file = runtime_storage.projects_mapping[project_name]
    project_cache = runtime_storage.project_cache
    if project_file not in project_cache or current_time - project_cache[project_file][1] > cache_timeout:
        logger.debug('Loading project file for %s at %s' % (project_name, project_file))
        try:
            project = load_config(project_file)["project"]
            project_cache[project_file] = [project, current_time]
        except Exception:
            # Project not found
            return None, None
    else:
        project = project_cache[project_file][0]
        project_cache[project_file][1] = current_time

    # Resolve service - simply return the service name again if found, otherwise just the project
    if service_name in project["app"]["services"]:
        return project, service_name
    return project, None


def get_all_projects(runtime_storage, logger) -> List[Project]:
    """Loads all projects that are found in the projects.json. Always reloads all projects."""
    logger.debug("Project listing: Requested. Reloading all projects.")
    runtime_storage.projects_mapping = load_projects()
    current_time = time.time()
    for project_name, project_file in runtime_storage.projects_mapping.items():
        logger.debug("Project listing: Processing %s : %s" % (project_name, project_file))
        try:
            project = load_config(project_file)["project"]
            runtime_storage.project_cache[project_file] = [project, current_time]
        except Exception as err:
            # Project could not be loaded
            logger.warn("Project listing: Could not load %s. Reason: %s" % (project_name, str(err)))
    return [tupl[0] for tupl in runtime_storage.project_cache.values()]


def resolve_container_address(project, service_name, engine, runtime_storage, logger):
    cache_timeout = 120  ## TODO CONFIGURABLE
    key = project["name"] + DOMAIN_PROJECT_SERVICE_SEP + service_name
    current_time = time.time()
    ip_cache = runtime_storage.ip_cache
    if key not in ip_cache or current_time - ip_cache[key][1] > cache_timeout:
        address = engine.address_for(project, service_name)
        logger.debug('Got container address for %s: %s' % (key, address))
        if address:
            address = "http://" + address[0] + ":" + str(address[1])
            # Only cache if we actually got something.
            ip_cache[key] = [address, current_time]
    else:
        address = ip_cache[key][0]
        ip_cache[key][1] = current_time
    return address
