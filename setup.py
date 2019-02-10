from setuptools import setup, find_packages

setup(
    name='riptide_proxy',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'tornado >= 5.1',
        'Click >= 7.0',
        # todo
    ],
    entry_points='''
        [console_scripts]
        riptide_proxy=riptide_proxy.main:main
    ''',
)