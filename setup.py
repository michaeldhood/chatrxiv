"""
Setup script for the chatrxiv package.
"""
from setuptools import setup, find_packages

setup(
    name="chatrxiv",
    version="0.1.0",
    description="Tools for extracting and processing Cursor AI chat logs",
    author="Cursor User",
    author_email="user@example.com",
    url="https://github.com/michaeldhood/chatrxiv",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.0.0",
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.0.0",
        "dlt[rest_api]>=1.0.0",
        "watchdog>=3.0.0",
        "click>=8.0.0",
        "anthropic>=0.34.0",
        "matplotlib>=3.5.0",
        "fastmcp>=2.14.5",
        "mcp>=1.24.0",
        "asyncpg>=0.31.0",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "chatrxiv=src.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
) 