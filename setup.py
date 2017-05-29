#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prototype of central drone API.
"""

import codecs
import io

from setuptools import setup, find_packages

long_description = codecs.open('README.md', "r", "utf-8").read()


def is_pkg(line):
    return line and not line.startswith(('--', 'git', '#'))

with io.open('requirements.txt', encoding='utf-8') as reqs:
    install_requires = [l for l in reqs.read().split('\n') if is_pkg(l)]

VERSION = (1, 0, 1)

setup(
    name="suav",
    version=".".join(map(str, VERSION)),
    author='Etalab',
    author_email='yohan.boniface@data.gouv.fr',
    description=__doc__,
    keywords="opendata drones",
    url='https://github.com/etalab/api-drones',
    packages=find_packages(),
    include_package_data=True,
    platforms=["any"],
    zip_safe=True,
    long_description=long_description,
    install_requires=install_requires,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python",
    ],
 )
