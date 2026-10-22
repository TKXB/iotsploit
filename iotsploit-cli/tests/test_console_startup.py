"""Saved targets must not prevent the shell from opening.

The console uses xlog, whose second argument is a logger name, not a format
value. Exercise the real constructor and logger with a temporary database.
Run in a subprocess because importing the console initializes Django and
changes process-wide logging and exception handling.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = [pytest.mark.django, pytest.mark.integration, pytest.mark.contract]


@pytest.mark.parametrize("saved_targets", [0, 1])
def test_shell_opens_with_saved_targets(tmp_path, saved_targets):
    cli_src = str(Path(__file__).resolve().parents[1] / "src")
    env = {
        **os.environ,
        "IOTSPLOIT_DATABASE_PATH": str(tmp_path / "startup.sqlite3"),
        "IOTSPLOIT_RUNTIME": "local",
        "PYTHONPATH": os.pathsep.join([cli_src, os.environ.get("PYTHONPATH", "")]),
    }
    script = """
import sys
from types import SimpleNamespace
from iotsploit_cli import console
from iotsploit_core.domain.target import Vehicle

# Startup logging must use the real wrapper, but does not need tool probing.
console.get_exploit_plugin_manager = lambda: SimpleNamespace(initialize=lambda: None)
manager = console.TargetManager.get_instance()
for index in range(int(sys.argv[1])):
    manager.save_target(Vehicle(target_id=f"target-{index}", name="Saved target", type="vehicle"))

shell = console.SAT_Shell()
assert len(shell.target_manager.get_all_targets()) == int(sys.argv[1])
assert shell.onecmd_plus_hooks("exit") is True
print("Shell startup succeeded")
"""

    result = subprocess.run(
        [sys.executable, "-c", script, str(saved_targets)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Shell startup succeeded" in result.stdout


def test_shell_startup_applies_pending_migrations_to_an_existing_database(tmp_path):
    """An existing database is migrated, not only a fresh one."""
    database = tmp_path / "existing.sqlite3"
    env = {**os.environ, "IOTSPLOIT_DATABASE_PATH": str(database), "IOTSPLOIT_RUNTIME": "local"}
    roll_back = """
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()
from django.core.management import call_command
call_command("migrate", interactive=False, verbosity=0)
call_command("migrate", "iotsploit_django", "0006", interactive=False, verbosity=0)
"""
    subprocess.run([sys.executable, "-c", roll_back], cwd=tmp_path, env=env, check=True, timeout=60)

    result = subprocess.run(
        [sys.executable, "-c", "from iotsploit_cli import console"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "iotsploit_django.0007_assistantsession_assistantevent_and_more" in result.stdout
    assert list(tmp_path.glob("existing.sqlite3.bak-*"))
    import sqlite3

    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name FROM django_migrations WHERE name LIKE '0007_%'").fetchone()
