"""`exec <plugin name>` must work, not just the interactive menu.

cmd2 passes a Statement, not a str. It compares equal to its own text, so the
membership check passes and the bug hides -- but Statement hashes a tuple
containing a list, so the first dict lookup raises TypeError: unhashable type:
'list'. Named execution was unusable until the argument was flattened.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from iotsploit_cli.commands import plugin_commands
from iotsploit_cli.commands.plugin_commands import PluginCommands
from iotsploit_core.platforms.capability import Availability

pytestmark = pytest.mark.unit


class FakePluginManager:
    def __init__(self):
        self.asked_for = None

    def list_plugins(self):
        return ["Interactive Demo", "Nmap Scan"]

    def plugin_availability(self, name):
        return Availability(True)

    def get_plugin(self, name):
        # The real manager does exactly this, which is where a Statement blows up.
        self.asked_for = {name: True}
        return None


class Shell(PluginCommands):
    """Only what do_execute_plugin touches."""

    def __init__(self, manager):
        self.plugin_manager = manager
        self.target_manager = None

    def poutput(self, message="", *, end="\n"):
        pass

    def perror(self, message="", *, end="\n", apply_style=True):
        pass

    def pwarning(self, message="", *, end="\n", apply_style=True):
        pass


def statement(text):
    """A cmd2 Statement, as the real shell builds it."""
    import cmd2

    return cmd2.parsing.StatementParser().parse(f"exec {text}")


def test_statement_is_unhashable_so_the_flattening_is_load_bearing():
    with pytest.raises(TypeError, match="unhashable"):
        {statement("Interactive Demo"): 1}


def test_named_execution_reaches_the_manager():
    manager = FakePluginManager()
    Shell(manager).do_execute_plugin(statement("Interactive Demo"))

    assert manager.asked_for == {"Interactive Demo": True}


def test_an_unknown_name_stops_before_the_manager():
    manager = FakePluginManager()
    Shell(manager).do_execute_plugin(statement("No Such Plugin"))

    assert manager.asked_for is None


class CapturingShell(PluginCommands):
    """Records printed lines, for the list and result output."""

    def __init__(self, manager):
        self.plugin_manager = manager
        self.target_manager = None
        self.lines = []

    def poutput(self, message="", *, end="\n"):
        self.lines.append(str(message))

    def perror(self, message="", *, end="\n", apply_style=True):
        self.lines.append(str(message))

    def pwarning(self, message="", *, end="\n", apply_style=True):
        self.lines.append(str(message))


@pytest.mark.parametrize(("status", "result", "error", "expected"), [
    ("completed", {"status": "success", "message": "Done"}, None, "✓ Demo"),
    ("completed", {"status": "error", "message": "Refused"}, None, "✗ Demo"),
    ("completed", {"success": False, "message": "Refused"}, None, "✗ Demo"),
    ("failed", None, {"message": "worker crashed", "reason": "error"}, "✗ Demo"),
    ("cancelled", None, {"reason": "operator"}, "✗ Demo"),
    ("expired", None, {"message": "worker lost", "reason": "timeout"}, "✗ Demo"),
    ("running", None, None, "Timeout waiting for task to complete"),
])
def test_async_result_mark_reflects_execution_outcome(monkeypatch, status, result, error, expected):
    execution = SimpleNamespace(status=status, is_terminal=status != "running", result=result, error=error)
    monkeypatch.setitem(sys.modules, "iotsploit_django.adapters.django.interaction.models", SimpleNamespace(
        ExecutionStatus=SimpleNamespace(COMPLETED="completed"),
        PluginExecution=SimpleNamespace(objects=SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(first=lambda: execution),
        )),
    ))
    # Expire the polling deadline without waiting or touching a real execution.
    times = iter([0, 301])
    monkeypatch.setitem(sys.modules, "time", SimpleNamespace(time=lambda: next(times), sleep=lambda _: None))
    monkeypatch.setattr(plugin_commands, "Input_Mgr", SimpleNamespace(
        Instance=lambda: SimpleNamespace(yes_no_input=lambda *args, **kwargs: True),
    ))
    manager = SimpleNamespace(
        list_plugins=lambda: ["Demo"],
        plugin_availability=lambda name: Availability(True),
        get_plugin=lambda name: SimpleNamespace(get_info=lambda: {}),
        execute_plugin=lambda *args, **kwargs: {"execution_type": "async", "task_id": "demo-task"},
    )
    shell = CapturingShell(manager)
    shell.target_manager = SimpleNamespace(get_current_target=lambda: None)

    shell.do_execute_plugin("Demo")

    text = "\n".join(shell.lines)
    assert expected in text
    if status != "completed" or result.get("status") == "error" or result.get("success") is False:
        assert "✓ Demo" not in text
    if status == "running":
        assert "✗ Demo" not in text


class ListingManager(FakePluginManager):
    def __init__(self, available):
        super().__init__()
        self._available = available
        self.plugin_registry = {name: {"description": f"does {name}"} for name in self.list_plugins()}

    def plugin_availability(self, name):
        ok = self._available.get(name, True)
        return Availability(True) if ok else Availability(False, reason="'adb' not on PATH")

    def get_plugin(self, name):
        raise AssertionError("Listing plugins must not load them")


def test_plugin_list_is_a_table_with_availability_and_a_count():
    manager = ListingManager({"Interactive Demo": True, "Nmap Scan": False})
    shell = CapturingShell(manager)

    shell.do_list_plugins("")

    table = "\n".join(shell.lines)
    assert "PLUGIN" in table and "AVAILABLE" in table
    assert "'adb' not on PATH" in table
    assert "does Interactive Demo" in table
    assert "2 plugins · 1 available" in shell.lines
