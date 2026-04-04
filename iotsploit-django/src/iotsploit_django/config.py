# Global configuration settings (iotsploit-django)
from __future__ import annotations

from pathlib import Path

import os

# repo root (workspace root). File lives at:
#   <repo>/iotsploit-django/src/iotsploit_django/config.py
# So parents[3] is the actual repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

# Optional override paths for legacy plugin directories (entry points are the default).
# Set these environment variables to re-enable legacy filesystem plugin discovery.
DEVICE_PLUGINS_DIR = os.getenv("IOTSPLOIT_DEVICE_PLUGINS_DIR") or os.getenv("SAT_DEVICE_PLUGINS_DIR")
EXPLOIT_PLUGINS_DIR = os.getenv("IOTSPLOIT_EXPLOIT_PLUGINS_DIR") or os.getenv("SAT_EXPLOIT_PLUGINS_DIR")


