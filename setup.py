#!/usr/bin/env python

from setuptools import setup, find_packages


test_dependencies = [
    'gisdata>=0.5.4',
    'geoserver-restconfig>=1.0.1',
    'psycopg2',
    'OWSLib>=0.7.2,<0.9.0',
    'unittest2',
    'pytest'
]


setup(name = "gn_gsimporter",
    version = "2.0.0c",
    description = "GeoNode GeoServer Importer Client",
    keywords = "GeoNode GeoServer Importer",
    license = "MIT",
    url = "https://github.com/GeoNode/gsimporter",
    author = "Ian Schneider",
    author_email = "ischneider@opengeo.org",
    install_requires = [
        'httplib2',
        'urllib3',
        'six'
    ],
    tests_require = test_dependencies,
    extras_require = {
            'testing': test_dependencies
    },
    packages=find_packages(),
    include_package_data = True,
    zip_safe = False,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering :: GIS',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    test_suite = 'test.uploadtests'
)
