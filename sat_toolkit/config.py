# Global configuration settings
from pathlib import Path

# Get project root directory (parent of config.py)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Global configuration settings

# Path to the device plugins directory
DEVICE_PLUGINS_DIR = str(PROJECT_ROOT / "plugins/devices")
EXPLOIT_PLUGINS_DIR = str(PROJECT_ROOT / "plugins/exploits")

