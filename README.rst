|Riptide|
=========

.. |Riptide| image:: https://riptide-docs.readthedocs.io/en/latest/_images/logo.png
    :alt: Riptide

.. class:: center

    ======================  ===================  ===================  ===================
    *Main packages:*        lib_                 **proxy**            cli_
    *Container-Backends:*   engine_docker_
    *Database Drivers:*     db_mysql_            db_mongo_
    *Plugins:*              php_xdebug_
    *Related Projects:*     configcrunch_
    *More:*                 docs_                repo_                docker_images_
    \                       mission_control_
    ======================  ===================  ===================  ===================

.. _lib:            https://github.com/theCapypara/riptide-lib
.. _cli:            https://github.com/theCapypara/riptide-cli
.. _proxy:          https://github.com/theCapypara/riptide-proxy
.. _configcrunch:   https://github.com/theCapypara/configcrunch
.. _engine_docker:  https://github.com/theCapypara/riptide-engine-docker
.. _db_mysql:       https://github.com/theCapypara/riptide-db-mysql
.. _db_mongo:       https://github.com/theCapypara/riptide-db-mongo
.. _docs:           https://github.com/theCapypara/riptide-docs
.. _repo:           https://github.com/theCapypara/riptide-repo
.. _docker_images:  https://github.com/theCapypara/riptide-docker-images
.. _mission_control: https://github.com/theCapypara/riptide-mission-control
.. _php_xdebug:     https://github.com/theCapypara/riptide-plugin-php-xdebug
.. _k8s_client:     https://github.com/theCapypara/riptide-k8s-client
.. _k8s_controller: https://github.com/theCapypara/riptide-k8s-controller

|build| |docs| |pypi-version| |pypi-downloads| |pypi-license| |pypi-pyversions|

.. |build| image:: https://img.shields.io/github/actions/workflow/status/theCapypara/riptide-proxy/build.yml
    :target: https://github.com/theCapypara/riptide-proxy/actions
    :alt: Build Status

.. |docs| image:: https://readthedocs.org/projects/riptide-docs/badge/?version=latest
    :target: https://riptide-docs.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

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