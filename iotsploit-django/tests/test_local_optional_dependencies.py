from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.contract


def test_local_startup_does_not_import_distributed_dependencies():
    script = r'''
import builtins
import os

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in {"celery", "redis", "channels_redis"}:
        raise AssertionError(f"distributed dependency imported: {name}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
os.environ["IOTSPLOIT_RUNTIME"] = "local"
os.environ["DJANGO_SETTINGS_MODULE"] = "iotsploit_django.settings.dev"

import django
django.setup()
import iotsploit_django.asgi
from iotsploit_django.adapters.django.stream_manager import DjangoStreamManager
DjangoStreamManager()
'''
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(project_root / "iotsploit-django" / "src"),
            str(project_root / "iotsploit-core" / "src"),
            str(project_root / "iotsploit-protocols" / "src"),
            env.get("PYTHONPATH", ""),
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr
