|Riptide|
=========

.. |Riptide| image:: https://riptide-docs.readthedocs.io/en/latest/_images/logo.png
    :alt: Riptide

.. class:: center

    ======================  ===================  ===================  ===================
    *Main packages:*        lib_                 **proxy**            cli_
    *Container-Backends:*   engine_docker_
    *Database Drivers:*     db_mysql_
    *Plugins:*              php_xdebug_
    *Related Projects:*     configcrunch_
    *More:*                 docs_                repo_                docker_images_
    \                       mission_control_
    ======================  ===================  ===================  ===================

.. _lib:            https://github.com/Parakoopa/riptide-lib
.. _cli:            https://github.com/Parakoopa/riptide-cli
.. _proxy:          https://github.com/Parakoopa/riptide-proxy
.. _configcrunch:   https://github.com/Parakoopa/configcrunch
.. _engine_docker:  https://github.com/Parakoopa/riptide-engine-docker
.. _db_mysql:       https://github.com/Parakoopa/riptide-db-mysql
.. _docs:           https://github.com/Parakoopa/riptide-docs
.. _repo:           https://github.com/Parakoopa/riptide-repo
.. _docker_images:  https://github.com/Parakoopa/riptide-docker-images
.. _mission_control: https://github.com/Parakoopa/riptide-mission-control
.. _php_xdebug:     https://github.com/Parakoopa/riptide-plugin-php-xdebug

|build| |docs| |pypi-version| |pypi-downloads| |pypi-license| |pypi-pyversions| |slack|

.. |build| image:: https://jenkins.riptide.parakoopa.de/buildStatus/icon?job=riptide-proxy%2Fmaster
    :target: https://jenkins.riptide.parakoopa.de/blue/organizations/jenkins/riptide-proxy/activity
    :alt: Build Status

.. |docs| image:: https://readthedocs.org/projects/riptide-docs/badge/?version=latest
    :target: https://riptide-docs.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

.. |slack| image:: https://slack.riptide.parakoopa.de/badge.svg
    :target: https://slack.riptide.parakoopa.de
    :alt: Join our Slack workspace

.. |pypi-version| image:: https://img.shields.io/pypi/v/riptide-proxy
    :target: https://pypi.org/project/riptide-proxy/
    :alt: Version

.. |pypi-downloads| image:: https://img.shields.io/pypi/dm/riptide-proxy
    :target: https://pypi.org/project/riptide-proxy/
    :alt: Downloads

.. |pypi-license| image:: https://img.shields.io/pypi/l/riptide-proxy
    :alt: License (MIT)

.. |pypi-pyversions| image:: https://img.shields.io/pypi/pyversions/riptide-proxy
    :alt: Supported Python versions

Riptide is a set of tools to manage development environments for web applications.
It's using container virtualization tools, such as `Docker <https://www.docker.com/>`_
to run all services needed for a project.

It's goal is to be easy to use by developers.
Riptide abstracts the virtualization in such a way that the environment behaves exactly
as if you were running it natively, without the need to install any other requirements
the project may have.

It can be installed via pip by installing ``riptide-proxy``.

Proxy Server
------------

This repository implements a HTTP(s) and WebSocket reverse proxy server for use with Riptide projects.
It supports auto-starting of Riptide projects. Routing of projects is based on hostnames.

If ``riptide-mission-control`` is installed, a proxy server for it is started at ``control.riptide.local``
(where riptide.local is your configured proxy server URL).

for-docs Branch
---------------

The for-docs branch should always be based on master. It contains only one commit that removes
python-prctl and certauth from the dependencies for Read the Docs, since rtd can't install them.

If anyone knows of a better way to do this, please let me know.

Documentation
-------------

The complete documentation for Riptide can be found at `Read the Docs <https://riptide-docs.readthedocs.io/en/latest/>`_.