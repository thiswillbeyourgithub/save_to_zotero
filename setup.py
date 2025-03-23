"""
Setup script for save_to_zotero package.
"""

from setuptools import setup, find_packages


setup(
    name="save_to_zotero",
    version="0.1.0",,
    description="Save webpages as PDFs and add them to Zotero",
    author="save_to_zotero",
    author_email="",  # Add your email
    url="https://github.com/yourusername/save_to_zotero",  # Change this to your repo
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fire==0.7.0",
        "pyzotero==1.6.11",
        "playwright==1.51.0",
        "requests==2.32.3",
        "PyPDF2==3.0.1",
        "loguru==0.7.3",
        "platformdirs==4.3.7",
        "bibtexparser==1.4.3",
        "feedparser==6.0.11",
        "httpx==0.28.1",
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
