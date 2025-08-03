"""Module to load projects and services using riptide-lib"""

from __future__ import annotations

import logging
import time
from enum import Enum
from types import SimpleNamespace
from typing import Any, Generic, TypeVar

from riptide.config.document.project import Project
from riptide.config.document.service import DOMAIN_PROJECT_SERVICE_SEP
from riptide.config.loader import load_config, load_projects
from riptide.engine.abstract import AbstractEngine
from riptide_proxy import CNT_ADRESS_CACHE_TIMEOUT, LOGGER_NAME, PROJECT_CACHE_TIMEOUT

logger = logging.getLogger(LOGGER_NAME)
T = TypeVar("T")


class CacheEntry(SimpleNamespace, Generic[T]):
    data: T
    time: float


class RuntimeStorage:
    def __init__(
        self,
        projects_mapping: dict[str, str],
        project_cache: dict[str, CacheEntry[Project]],
        ip_cache: dict[str, CacheEntry[str]],
        engine: AbstractEngine,
        use_compression=False,
    ):
        self.projects_mapping = projects_mapping
        # A cache of projects. Contains a mapping (project file path) => [project object, age]
        self.project_cache = project_cache
        # A cache of ip addresses for services. Contains a mapping (project_name + "__" + service_name) => [address, age]
        self.ip_cache = ip_cache
        self.engine = engine
        self.use_compression = use_compression


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


def resolve_project(
    hostname, base_url: str, runtime_storage: RuntimeStorage, autostart=True
) -> tuple[ResolveStatus, Any]:
    """
    Resolve the project and service based on the the hostname, base url
    and available Riptide projects, as reported by riptide-cli

    :param runtime_storage: Runtime storage object
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
        assert resolved_service_name is not None
        address = _resolve_container_address(project, resolved_service_name, runtime_storage)

        if address is not None:
            # PROXY
            return ResolveStatus.SUCCESS, (project, resolved_service_name, address)
        elif autostart:
            return ResolveStatus.NOT_STARTED_AUTOSTART, (project, resolved_service_name)
        else:
            return ResolveStatus.NOT_STARTED, (project, resolved_service_name)

    else:
        return ResolveStatus.PROJECT_NOT_FOUND, project_name


def get_all_projects(runtime_storage: RuntimeStorage) -> tuple[list[Project], list[ProjectLoadError]]:
    """Loads all projects that are found in the projects.json. Always reloads all projects."""
    logger.debug("Project listing: Requested. Reloading all projects.")
    runtime_storage.projects_mapping = load_projects(True)
    current_time = time.time()
    errors = []
    for project_name, project_file in runtime_storage.projects_mapping.items():
        logger.debug(f"Project listing: Processing {project_name} : {project_file}")
        try:
            try:
                project = _load_single_project(project_file, runtime_storage.engine)
                runtime_storage.project_cache[project_file] = CacheEntry(data=project, time=current_time)
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

    return sorted((tupl.data for tupl in runtime_storage.project_cache.values()), key=lambda p: p["name"]), errors


def _load_single_project(project_file: str, engine: AbstractEngine) -> Project:
    config = load_config(project_file)
    config.load_performance_options(engine)
    if "project" in config:
        return config["project"]
    raise FileNotFoundError(f"Project file ({project_file}) not found.")


def _extract_names_from(hostname: str, base_url: str) -> tuple[str | None, str | None]:
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


def load_project_and_service(
    project_name: str, service_name: str | None, runtime_storage: RuntimeStorage
) -> tuple[Project | None, str | None]:
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
            logger.debug(f"Could not find project {project_name}")
            # Project not found
            return None, None

    # Load project from cache. Cache times out after some time.
    current_time = time.time()
    project_file = runtime_storage.projects_mapping[project_name]
    project_cache = runtime_storage.project_cache
    if project_file not in project_cache or current_time - project_cache[project_file].time > PROJECT_CACHE_TIMEOUT:
        logger.debug(f"Loading project file for {project_name} at {project_file}")
        try:
            project = _load_single_project(project_file, runtime_storage.engine)
            project_cache[project_file] = CacheEntry(data=project, time=current_time)
        except FileNotFoundError:
            # Project not found
            return None, None
        except Exception as ex:
            # Load error :(
            raise ProjectLoadError(project_name) from ex
    else:
        project = project_cache[project_file].data
        project_cache[project_file].time = current_time

    # Resolve service - simply return the service name again if found, otherwise just the project
    if service_name in project["app"]["services"]:
        return project, service_name
    return project, None


def _resolve_container_address(project: Project, service_name: str, runtime_storage: RuntimeStorage) -> str | None:
    key = project["name"] + DOMAIN_PROJECT_SERVICE_SEP + service_name
    current_time = time.time()
    ip_cache = runtime_storage.ip_cache
    if key not in ip_cache or current_time - ip_cache[key].time > CNT_ADRESS_CACHE_TIMEOUT:
        address = runtime_storage.engine.address_for(project, service_name)
        logger.debug(f"Got container address for {key}: {address}")
        if address is not None:
            addressstr = "http://" + address[0] + ":" + str(address[1])
            # Only cache if we actually got something.
            ip_cache[key] = CacheEntry(data=addressstr, time=current_time)
        else:
            return None
    else:
        addressstr = ip_cache[key].data
        ip_cache[key].time = current_time
    return addressstr
