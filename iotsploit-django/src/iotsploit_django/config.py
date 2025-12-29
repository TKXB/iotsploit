# Global configuration settings (iotsploit-django)
from __future__ import annotations

from pathlib import Path

# repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Path to the device plugins directory
DEVICE_PLUGINS_DIR = str(PROJECT_ROOT / "plugins" / "devices")
EXPLOIT_PLUGINS_DIR = str(PROJECT_ROOT / "plugins" / "exploits")


