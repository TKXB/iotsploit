# Global configuration settings (iotsploit-django)
from __future__ import annotations

from pathlib import Path

import os

# repo root (workspace root). File lives at:
#   <repo>/iotsploit-django/src/iotsploit_django/config.py
# So parents[3] is the actual repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

# Path to the plugins directories (allow env override, consistent with iotsploit-core)
DEVICE_PLUGINS_DIR = os.getenv("IOTSPLOIT_DEVICE_PLUGINS_DIR") or os.getenv("SAT_DEVICE_PLUGINS_DIR") or str(
    REPO_ROOT / "plugins" / "devices"
)
EXPLOIT_PLUGINS_DIR = os.getenv("IOTSPLOIT_EXPLOIT_PLUGINS_DIR") or os.getenv("SAT_EXPLOIT_PLUGINS_DIR") or str(
    REPO_ROOT / "plugins" / "exploits"
)


