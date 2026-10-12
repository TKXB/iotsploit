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
