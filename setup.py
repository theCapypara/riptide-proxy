from setuptools import setup, find_packages
import sys
import subprocess
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.egg_info import egg_info

# README read-in
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()
# END README read-in


# Additional packages, that rely on system features in order to be installable.
# Don't fail on errors, but tell the user that installation failed.
# This is mainly to be able to install it on Read the Docs, and is otherwise not supported.
ADDITIONAL_REQS_PRCTL = 'python-prctl >= 1.7; sys_platform == "linux"'
ADDITIONAL_REQS_CERTAUTH = 'certauth >= 1.2'


def additional_requirements():
    # LINUX: prctl
    print('-------------')
    print('riptide-proxy: Installing additional requirement: ' + ADDITIONAL_REQS_PRCTL)
    retcode = subprocess.call([sys.executable, "-m", "pip", "install", ADDITIONAL_REQS_PRCTL])
    if retcode != 0:
        print('!!! WARNING: Could not install python-prctl. Running with sudo impossible, the proxy may or may '
              'not work correctly! Please install prctl-dev and reinstall the proxy server.')

    # ALL PLATFORMS: cerauth
    print('-------------')
    print('riptide-proxy: Installing additional requirement: ' + ADDITIONAL_REQS_CERTAUTH)
    retcode = subprocess.call([sys.executable, "-m", "pip", "install", ADDITIONAL_REQS_CERTAUTH])
    if retcode != 0:
        print('!!! WARNING: Could not install certauth. HTTPS impossible to use, the proxy may or may '
              'not work correctly! Please fix OpenSSL setup and reinstall the proxy server.')
    print('-------------')


class AdditionalRequirementsInstall(install):
    def run(self):
        additional_requirements()
        install.run(self)


class AdditionalRequirementsDevelop(develop):
    def run(self):
        additional_requirements()
        develop.run(self)


class AdditionalRequirementsEggInfo(egg_info):
    def run(self):
        additional_requirements()
        egg_info.run(self)


setup(
    name='riptide-proxy',
    version='0.2.1',
    packages=find_packages(),
    package_data={'riptide_proxy': ['tpl/*']},
    description='Tool to manage development environments for web applications using containers - HTTP and WebSocket Reverse Proxy Server',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    url='https://github.com/Parakoopa/riptide-proxy/',
    install_requires=[
        'riptide-lib >= 0.2, < 0.3',
        'tornado >= 5.1',
        'Click >= 7.0',
        'recordclass >= 0.7'
    ],
    # The additional requirements are also in extras_require to be parsable by tools.
    extras_require={'extras': [
        ADDITIONAL_REQS_CERTAUTH,
        ADDITIONAL_REQS_PRCTL
    ]},
    cmdclass={
        'install': AdditionalRequirementsInstall,
        'develop': AdditionalRequirementsDevelop,
        'egg_info': AdditionalRequirementsEggInfo,
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    entry_points='''
        [console_scripts]
        riptide_proxy=riptide_proxy.main:main
    ''',
)
