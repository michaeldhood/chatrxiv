"""
Main entry point for running the package as a module.

Uses the Click-based CLI from src/cli/.
"""
import sys

# Monkey-patch early for gevent SSE support in web command
# Must happen BEFORE importing anything that touches ssl/socket
if len(sys.argv) > 1 and sys.argv[1] == 'web':
    from gevent import monkey
    monkey.patch_all()

# New Click-based CLI from src/cli/__init__.py
from src.cli import main

if __name__ == "__main__":
    sys.exit(main())

