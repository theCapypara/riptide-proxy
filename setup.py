from setuptools import setup, find_packages

setup(
    name='riptide_proxy',
    version='0.1',
    packages=find_packages(),
    description='TODO',  # TODO
    long_description='TODO',  # TODO
    install_requires=[
        'riptide_lib == 0.1',
        'tornado >= 5.1',
        'Click >= 7.0',
        'recordclass >= 0.7',
        'python-prctl >= 1.7; sys_platform == "linux"',
        'certauth >= 1.2',
    ],
    # TODO
    classifiers=[
        'Programming Language :: Python',
    ],
    entry_points='''
        [console_scripts]
        riptide_proxy=riptide_proxy.main:main
    ''',
)
