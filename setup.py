from setuptools import setup, find_packages

setup(
    name='riptide_proxy',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    description='TODO',  # TODO
    long_description='TODO - Project will be available starting May/June',  # TODO
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
        'Development Status :: 4 - Beta',
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
