"""
Setup script for save_to_zotero package.
"""

from setuptools import setup, find_packages

# Get version from package
with open("save_to_zotero/save_to_zotero.py", "r") as f:
    for line in f:
        if line.startswith("    VERSION: str ="):
            version = line.split("=")[1].strip().strip('"\'')
            break

setup(
    name="save_to_zotero",
    version=version,
    description="Save webpages as PDFs and add them to Zotero",
    author="save_to_zotero",
    author_email="",  # Add your email
    url="https://github.com/yourusername/save_to_zotero",  # Change this to your repo
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fire",
        "pyzotero",
        "playwright",
        "requests",
        "PyPDF2",
        "loguru",
        "platformdirs",
    ],
    entry_points={
        "console_scripts": [
            "save-to-zotero=save_to_zotero.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
)
