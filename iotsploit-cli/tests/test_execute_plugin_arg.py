"""`exec <plugin name>` must work, not just the interactive menu.

cmd2 passes a Statement, not a str. It compares equal to its own text, so the
membership check passes and the bug hides -- but Statement hashes a tuple
containing a list, so the first dict lookup raises TypeError: unhashable type:
'list'. Named execution was unusable until the argument was flattened.
"""

from __future__ import annotations

import pytest

from iotsploit_cli.commands.plugin_commands import PluginCommands

pytestmark = pytest.mark.unit


class FakePluginManager:
    def __init__(self):
        self.asked_for = None

    def list_plugins(self):
        return ["Interactive Demo", "Nmap Scan"]

    def get_plugin(self, name):
        # The real manager does exactly this, which is where a Statement blows up.
        self.asked_for = {name: True}
        return None


class Shell(PluginCommands):
    """Only what do_execute_plugin touches."""

    def __init__(self, manager):
        self.plugin_manager = manager
        self.target_manager = None


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
