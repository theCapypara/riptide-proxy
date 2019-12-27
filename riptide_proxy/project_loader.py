"""Module to load projects and services using riptide-lib"""
import time

import logging
from enum import Enum
from typing import Tuple, Union, Dict, List, NamedTuple

from riptide.config.document.project import Project
from riptide.config.document.service import Service, DOMAIN_PROJECT_SERVICE_SEP
from riptide.config.loader import load_projects, load_config
from riptide.engine.abstract import AbstractEngine
from riptide_proxy import PROJECT_CACHE_TIMEOUT, LOGGER_NAME, CNT_ADRESS_CACHE_TIMEOUT

logger = logging.getLogger(LOGGER_NAME)


class RuntimeStorage:
    def __init__(self, projects_mapping: Dict, project_cache: Dict, ip_cache: Dict):
        self.projects_mapping = projects_mapping
        self.project_cache = project_cache
        self.ip_cache = ip_cache

    projects_mapping: Dict
    # A cache of projects. Contains a mapping (project file path) => [project object, age]
    project_cache: Dict
    # A cache of ip addresses for services. Contains a mapping (project_name + "__" + service_name) => [address, age]
    ip_cache: Dict


class ResolveStatus(Enum):
    SUCCESS = 0
    NO_PROJECT = 1
    NO_MAIN_SERVICE = 2
    SERVICE_NOT_FOUND = 3
    NOT_STARTED = 4
    NOT_STARTED_AUTOSTART = 5
    PROJECT_NOT_FOUND = 6


class ProjectLoadError(Exception):
    def __init__(self, project_name: str) -> None:
        self.project_name = project_name

    def __str__(self):
        return "Error loading project " + self.project_name


def resolve_project(hostname, base_url: str,
                    engine: AbstractEngine, runtime_storage: RuntimeStorage, autostart=True
                    ) -> Tuple[ResolveStatus, any]:
    """
    Resolve the project and service based on the the hostname, base url
    and available Riptide projects, as reported by riptide-cli

    :param runtime_storage: Runtime storage object
    :param engine: Engine to use
    :param hostname: Request hostname
    :param base_url: The configured proxy base url
    :param autostart: Whether or not autostart is enabled

    :raises  ProjectLoadError: On project load error
    :return: Depending on the result, this function may return various things.

             The format is always a tuple of ``ResolveStatus`` and a data object:

             ``ResolveStatus.SUCCESS``, (project, resolved_service_name, address):
                Project was found and service also. data is project, resolved service and container address

             ``ResolveStatus.NO_PROJECT``, None:
                No project or service was specified in the URL.

             ``ResolveStatus.NO_MAIN_SERVICE``, (Project, request_service_name):
                No service was specified, and the project has no main service.
                data is tuple of project and the requested service name.

             ``ResolveStatus.SERVICE_NOT_FOUND``, (Project, request_service_name):
                Service was not found. data is tuple of project and the requested service name.

             ``ResolveStatus.NOT_STARTED``, (Project, resolved_service_name):
                Service is not started, autostart is disabled. data is tuple of project and the service name.

             ``ResolveStatus.NOT_STARTED_AUTOSTART``, (Project, resolved_service_name):
                Service is not started, autostart is enabled. data is tuple of project and the service name.

             ``ResolveStatus.PROJECT_NOT_FOUND``, project_name:
                The project was not found. data is the name of the requested project.

    """
    # Get the requested project and service names from the URL
    project_name, request_service_name = _extract_names_from(hostname, base_url)
    if project_name is None:
        # No project specified
        return ResolveStatus.NO_PROJECT, None

    # Try to load a project
    project, resolved_service_name = load_project_and_service(project_name, request_service_name, runtime_storage)

    if project:
        # Project could be loaded
        if not resolved_service_name:
            # Service could not be loaded :(
            if not request_service_name:
                # ...but no service was specified. So instead: Load main service
                resolved_service_name = None
                main_service_obj = project["app"].get_service_by_role("main")
                if main_service_obj:
                    resolved_service_name = main_service_obj["$name"]
                if not resolved_service_name:
                    # Nope, main service could also not be loaded
                    return ResolveStatus.NO_MAIN_SERVICE, (project, request_service_name)
            else:
                # Service was not found :(
                return ResolveStatus.SERVICE_NOT_FOUND, (project, request_service_name)

        # Service and project are resolved
        # Resolve container address and proxy the request
        address = _resolve_container_address(project, resolved_service_name, engine, runtime_storage)

        if address:
            # PROXY
            return ResolveStatus.SUCCESS, (project, resolved_service_name, address)
        elif autostart:
            return ResolveStatus.NOT_STARTED_AUTOSTART, (project, resolved_service_name)
        else:
            return ResolveStatus.NOT_STARTED, (project, resolved_service_name)

    else:
        return ResolveStatus.PROJECT_NOT_FOUND, project_name


def get_all_projects(runtime_storage) -> Tuple[List[Project], List[ProjectLoadError]]:
    """Loads all projects that are found in the projects.json. Always reloads all projects."""
    logger.debug("Project listing: Requested. Reloading all projects.")
    runtime_storage.projects_mapping = load_projects()
    current_time = time.time()
    errors = []
    for project_name, project_file in runtime_storage.projects_mapping.items():
        logger.debug(f"Project listing: Processing {project_name} : {project_file}")
        try:
            try:
                project = _load_single_project(project_file)
                runtime_storage.project_cache[project_file] = [project, current_time]
            except FileNotFoundError as ex:
                # Project not found
                raise ProjectLoadError(project_name) from ex
            except Exception as ex:
                # Load error :(
                logger.warning(f"Project listing: Could not load {project_name}. Reason: {str(ex)}")
                # TODO: This is a bit ugly...
                raise ProjectLoadError(project_name) from ex
        except ProjectLoadError as load_error:
            errors.append(load_error)

    return [tupl[0] for tupl in runtime_storage.project_cache.values()], errors


def _load_single_project(project_file):
    config = load_config(project_file)
    if "project" in config:
        return config["project"]
    raise FileNotFoundError(f"Project file ({project_file}) not found.")


def _extract_names_from(hostname, base_url) -> Tuple[Union[str, None], Union[str, None]]:
    """
    Remove ports and base url from request and return project and service name

    :param hostname: Request hostname
    :param base_url: The configured proxy base url

    :return: tuple of project and service names. Both might be None,
             if only the base url was accessed, and service may be None.
    """
    real_host = hostname.split(":")[0]
    riptide_host_part = "".join(real_host.rsplit("." + base_url))
    if riptide_host_part == base_url:
        return None, None
    # Otherwise this should be a valid project URL, but make sure we only check the last part of the project name
    riptide_host_part = riptide_host_part.split(".")[-1]

    parts = riptide_host_part.split(DOMAIN_PROJECT_SERVICE_SEP)
    project_name = parts[0]
    request_service_name = None
    if len(parts) > 1:
        request_service_name = DOMAIN_PROJECT_SERVICE_SEP.join(parts[1:])

    return project_name, request_service_name


def load_project_and_service(project_name, service_name, runtime_storage: RuntimeStorage) \
        -> Tuple[Union[Project, None], Union[Service, None]]:
    """

    Resolves the project object and service name for the project identified by hostname
    Service name may be None if no service was specified, and project is None if no project could be loaded.

    :param project_name: Name of the requested project
    :param service_name: Name of the requested service
    :param runtime_storage: Runtime storage object
    :return: Tuple of loaded project and resolved service name. Both may be empty if either of them could not be
             resolved.
    """

    # Get project file
    if project_name not in runtime_storage.projects_mapping:
        # Try to reload. Maybe it was added?
        runtime_storage.projects_mapping = load_projects()
        if project_name not in runtime_storage.projects_mapping:
            logger.debug(f'Could not find project {project_name}')
            # Project not found
            return None, None

    # Load project from cache. Cache times out after some time.
    current_time = time.time()
    project_file = runtime_storage.projects_mapping[project_name]
    project_cache = runtime_storage.project_cache
    if project_file not in project_cache or current_time - project_cache[project_file][1] > PROJECT_CACHE_TIMEOUT:
        logger.debug(f'Loading project file for {project_name} at {project_file}')
        try:
            project = load_config(project_file)["project"]
            project_cache[project_file] = [project, current_time]
        except FileNotFoundError as ex:
            # Project not found
            return None, None
        except Exception as ex:
            # Load error :(
            raise ProjectLoadError(project_name) from ex
    else:
        project = project_cache[project_file][0]
        project_cache[project_file][1] = current_time

    # Resolve service - simply return the service name again if found, otherwise just the project
    if service_name in project["app"]["services"]:
        return project, service_name
    return project, None


def _resolve_container_address(project, service_name, engine, runtime_storage):
    key = project["name"] + DOMAIN_PROJECT_SERVICE_SEP + service_name
    current_time = time.time()
    ip_cache = runtime_storage.ip_cache
    if key not in ip_cache or current_time - ip_cache[key][1] > CNT_ADRESS_CACHE_TIMEOUT:
        address = engine.address_for(project, service_name)
        logger.debug(f'Got container address for {key}: {address}')
        if address:
            address = "http://" + address[0] + ":" + str(address[1])
            # Only cache if we actually got something.
            ip_cache[key] = [address, current_time]
    else:
        address = ip_cache[key][0]
        ip_cache[key][1] = current_time
    return address
