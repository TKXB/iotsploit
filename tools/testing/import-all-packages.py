#!/usr/bin/env python3
"""Import every module shipped by every IoTSploit Python package."""

from __future__ import annotations

import importlib
import os
import pkgutil


PACKAGES = (
    "iotsploit_core",
    "iotsploit_cli",
    "iotsploit_django",
    "iotsploit_drivers",
    "iotsploit_exploits",
    "iotsploit_fuzzer",
    "iotsploit_mcp",
    "iotsploit_platforms",
    "iotsploit_priv",
    "iotsploit_protocols",
)


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    os.environ.setdefault("SECRET_KEY", "import-smoke-test")
    os.environ.setdefault("ALLOWED_HOSTS", "localhost")
    os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost")
    for package_name in PACKAGES:
        package = importlib.import_module(package_name)
        for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            importlib.import_module(module.name)


if __name__ == "__main__":
    main()
