<h1>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://riptide-docs.readthedocs.io/en/latest/_images/logo_dark.png">
  <img alt="Riptide" src="https://riptide-docs.readthedocs.io/en/latest/_images/logo.png" width="300">
</picture>
</h1>

[<img src="https://img.shields.io/github/actions/workflow/status/theCapypara/riptide-proxy/build.yml" alt="Build Status">](https://github.com/theCapypara/riptide-proxy/actions)
[<img src="https://readthedocs.org/projects/riptide-docs/badge/?version=latest" alt="Documentation Status">](https://riptide-docs.readthedocs.io/en/latest/)
[<img src="https://img.shields.io/pypi/v/riptide-proxy" alt="Version">](https://pypi.org/project/riptide-proxy/)
[<img src="https://img.shields.io/pypi/dm/riptide-proxy" alt="Downloads">](https://pypi.org/project/riptide-proxy/)
<img src="https://img.shields.io/pypi/l/riptide-proxy" alt="License (MIT)">
<img src="https://img.shields.io/pypi/pyversions/riptide-proxy" alt="Supported Python versions">

Riptide is a set of tools to manage development environments for web applications.
It's using container virtualization tools, such as [Docker](https://www.docker.com/)
to run all services needed for a project.

Its goal is to be easy to use by developers.
Riptide abstracts the virtualization in such a way that the environment behaves exactly
as if you were running it natively, without the need to install any other requirements
the project may have.

Riptide consists of a few repositories, find the
entire [overview](https://riptide-docs.readthedocs.io/en/latest/development.html) in the documentation.

## Proxy Server

This repository implements a HTTP(s) and WebSocket reverse proxy server for use with Riptide projects.
It supports auto-starting of Riptide projects. Routing of projects is based on hostnames.

If `riptide-mission-control` is installed, a proxy server for it is started at `control.riptide.local`
(where riptide.local is your configured proxy server URL).

## for-docs Branch

The for-docs branch should always be based on master. It contains only one commit that removes
python-prctl and certauth from the dependencies for Read the Docs, since rtd can't install them.

If anyone knows of a better way to do this, please let me know.

## Documentation

The complete documentation for Riptide can be found at [Read the Docs](https://riptide-docs.readthedocs.io/en/latest/).
