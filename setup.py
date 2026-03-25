import re
from setuptools import setup, find_packages

with open("ldap_watchdog/__init__.py") as f:
    version = re.search(r'__version__\s*=\s*["\']([^"\']+)', f.read()).group(1)

with open("README.md") as f:
    long_description = f.read()

setup(
    name="LDAP-Monitor",
    version=version,
    description="Monitor LDAP directory changes in real-time",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Joshua Rogers",
    author_email="ldap-watchdog@joshua.hu",
    url="https://github.com/MegaManSec/LDAP-Monitoring-Watchdog",
    project_urls={
        "Blog Post": "https://joshua.hu/ldap-watchdog-openldap-python-monitoring-tool-realtime-directory-slack-notifications",
        "Author": "https://joshua.hu/",
    },
    license="GPL-3.0",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "ldap3",
    ],
    extras_require={
        "slack": ["requests"],
    },
    entry_points={
        "console_scripts": [
            "ldap-watchdog=ldap_watchdog.watchdog:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP",
    ],
)
