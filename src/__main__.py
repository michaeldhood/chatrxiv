"""
Main entry point for running the package as a module.

Uses the Click-based CLI from src/cli/.
"""
import sys

# New Click-based CLI from src/cli/__init__.py
from src.cli import main

if __name__ == "__main__":
    sys.exit(main())

