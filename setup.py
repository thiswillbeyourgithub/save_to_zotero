"""
Setup script for save_to_zotero package.
"""

import subprocess
import sys

from setuptools import setup, find_packages
from setuptools.command.install import install


class PostInstallCommand(install):
    """Post-installation command to install Playwright browsers."""

    def run(self):
        install.run(self)

        # Install Playwright browsers
        try:
            subprocess.check_call([sys.executable, "-m", "playwright", "install"])
        except Exception as err:
            print(f"Error when installing Playwright browsers: '{err}'")
            print("You may need to run 'python -m playwright install' manually")


# Read the README.md file for the long description
with open("README.md", "r") as readme:
    long_description = readme.read()

setup(
    name="save_to_zotero",
    version="1.1.2",
    description="Save webpages as PDFs and add them to Zotero",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="save_to_zotero",
    url="https://github.com/thiswillbeyourgithub/save_to_zotero",
    packages=find_packages(),
    include_package_data=True,
    license="GPLv3",
    keywords=[
        "zotero",
        "research",
        "publication",
        "journal",
        "paper",
        "upload",
        "pdf",
        "document",
        "archive",
        "omnivore",
        "hoarder",
        "highlight",
        "annotation",
    ],
    install_requires=[
        "fire>=0.7.0",
        "pyzotero>=1.6.11",
        "playwright>=1.51.0",
        "requests>=2.32.3",
        "loguru>=0.7.3",
        "platformdirs>=4.3.7",
    ],
    entry_points={
        "console_scripts": [
            "save-to-zotero=save_to_zotero.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
    cmdclass={
        "install": PostInstallCommand,
    },
)
