#!/usr/bin/env python
# Copyright 2014 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the
#    License. You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing,
#    software distributed under the License is distributed on an "AS
#    IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
#    express or implied. See the License for the specific language
#    governing permissions and limitations under the License.

import os
import sys

import setuptools


# Utility function to read the README file
def readfile(filename):
    with open(filename) as f:
        return f.read()


# Utility function to read requirements.txt files
def readreq(filename):
    result = []
    with open(filename) as f:
        for line in f:
            line = line.strip()

            # Process requirement file references
            if line.startswith('-r '):
                subfilename = line.split(None, 1)[-1].split('#', 1)[0].strip()
                if subfilename:
                    result += readreq(subfilename)
                continue

            # Strip out "-e" prefixes
            if line.startswith('-e '):
                line = line.split(None, 1)[-1]

            # Detect URLs in the line
            idx = line.find('#egg=')
            if idx >= 0:
                line = line[idx + 5:]

            # Strip off any comments
            line = line.split('#', 1)[0].strip()

            # Save the requirement
            if line:
                result.append(line.split('#', 1)[0].strip())

    return result


# Invoke setup
setuptools.setup(
    name='timid-github',
    version='0.1.0',
    author='Kevin L. Mitchell',
    author_email='kevin.mitchell@rackspace.com',
    url='https://github.com/rackerlabs/timid-github',
    description='Timid Github extension',
    long_description=readfile('README.rst'),
    license='Apache License (2.0)',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    py_modules=['timid_github'],
    install_requires=readreq('requirements.txt'),
    tests_require=readreq('test-requirements.txt'),
    entry_points={
        'timid.extensions': [
            'timid-github = timid_github:GithubExtension',
        ],
    },
)
