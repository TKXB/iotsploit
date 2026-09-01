from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from iotsploit_django.tools.privilege_mgr import PrivilegeManager

pytestmark = pytest.mark.unit


def test_privileged_result_uses_file_even_when_stdout_is_noisy(monkeypatch):
    expected = {"success": True, "message": "done"}

    def fake_run(command, **kwargs):
        with open(kwargs["env"]["RESULT_PATH"], "w", encoding="utf-8") as result_file:
            json.dump(expected, result_file)
        return SimpleNamespace(returncode=0, stdout="external tool noise\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    manager = PrivilegeManager()
    manager.has_sudo_access = True

    success, result = manager.run_plugin_with_sudo("example")

    assert success is True
    assert json.loads(result) == expected
