"""Shared pytest fixtures and path setup for iotsploit-cli tests.

This file ensures that ``iotsploit_cli`` is importable without requiring
Django initialization.  The ``command_palette`` module itself has no Django
dependency, so these tests can run in isolation.
"""

import sys
from pathlib import Path

# Ensure src/ is on sys.path so iotsploit_cli is importable even if the
# package has not been installed via pip/poetry in the current environment.
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
