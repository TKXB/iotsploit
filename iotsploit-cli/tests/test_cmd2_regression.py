"""Regression tests for cmd2 completion compatibility with the palette.

These tests verify that the command palette does not break existing cmd2
behaviour: argument completion, visible-command exclusions, and
first-token completion all work correctly.
"""

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

import cmd2
from iotsploit_cli.command_palette import (
    Cmd2CompletionAdapter,
    CommandCatalog,
    CommandPaletteCompleter,
)


# --------------------------------------------------------------------------- #
#  Test shell with real cmd2.Cmd
# --------------------------------------------------------------------------- #


class RegressionShell(cmd2.Cmd):
    """A real cmd2.Cmd with representative commands for regression testing."""

    def do_exploit(self, arg):
        """Execute all plugins in the IotSploit System"""
        pass

    def do_exit(self, arg):
        """Exit Console"""
        return True

    def do_edit(self, arg):
        """Edit the current command line"""
        pass

    def do_help(self, arg):
        """List available commands"""
        pass


@pytest.fixture
def shell():
    return RegressionShell()


@pytest.fixture
def catalog(shell):
    return CommandCatalog(shell)


@pytest.fixture
def adapter(shell):
    return Cmd2CompletionAdapter(shell)


@pytest.fixture
def completer(shell, catalog, adapter):
    return CommandPaletteCompleter(shell, catalog, adapter)


# --------------------------------------------------------------------------- #
#  Tab completion regression
# --------------------------------------------------------------------------- #


class TestCmd2TabCompletion:
    """Verify existing Tab completion still works through the adapter."""

    def test_adapter_completes_ex_prefix(self, adapter):
        """The adapter (used for argument Tab) returns exit and exploit for 'ex'."""
        doc = Document(text="ex", cursor_position=2)
        completions = list(adapter.get_completions(doc))
        names = [c.text for c in completions]
        assert "exit" in names
        assert "exploit" in names

    def test_tab_completes_any_prefix_via_palette(self, completer):
        """Tab on 'he' returns help via the palette (first-token context)."""
        doc = Document(text="he", cursor_position=2)
        event = CompleteEvent(completion_requested=True)
        completions = list(completer.get_completions(doc, event))
        names = [c.text for c in completions]
        assert "help" in names

    def test_tab_completes_full_command_name(self, adapter):
        """Tab on 'hel' should narrow to help only."""
        doc = Document(text="hel", cursor_position=3)
        completions = list(adapter.get_completions(doc))
        names = [c.text for c in completions]
        # cmd2 appends a space to single matches at end of line
        assert len(names) == 1
        assert names[0].startswith("help")

    def test_tab_no_matches_for_unknown(self, adapter):
        """Tab on 'zzz' should return no matches."""
        doc = Document(text="zzz", cursor_position=3)
        completions = list(adapter.get_completions(doc))
        assert completions == []


class TestVisibleCommandsExclusions:
    """Verify get_visible_commands() exclusions are honored."""

    def test_hidden_command_excluded_from_catalog(self, shell, catalog):
        shell.hidden_commands.append("exploit")
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exploit" not in names

    def test_disabled_command_excluded_from_catalog(self, shell, catalog):
        shell.disabled_commands["exit"] = True
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exit" not in names

    def test_hidden_command_still_in_visible(self, shell):
        """Verify cmd2 get_visible_commands works as expected."""
        all_cmds = set(shell.get_all_commands())
        visible = set(shell.get_visible_commands())
        assert "exploit" in all_cmds
        assert "exploit" in visible
        shell.hidden_commands.append("exploit")
        visible_after = set(shell.get_visible_commands())
        assert "exploit" not in visible_after


class TestPaletteFirstTokenActivation:
    """Verify the palette activates for any first-token prefix while typing."""

    def test_any_first_token_produces_results(self, completer):
        """Typing 'he' should produce palette auto-completions (help)."""
        doc = Document(text="he", cursor_position=2)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        completions = list(completer.get_completions(doc, event))
        names = [c.text for c in completions]
        assert "help" in names

    def test_command_with_space_no_auto(self, completer):
        """Typing 'help ' (cursor after space) should not produce palette results."""
        doc = Document(text="help ", cursor_position=5)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        completions = list(completer.get_completions(doc, event))
        assert completions == []

    def test_empty_input_no_auto(self, completer):
        """Empty input should not produce palette auto-completions."""
        doc = Document(text="", cursor_position=0)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        completions = list(completer.get_completions(doc, event))
        assert completions == []


class TestCmd2AdapterWithRealCmd2:
    """End-to-end tests with a real cmd2.Cmd instance."""

    def test_adapter_returns_cmd2_matches(self, shell, adapter):
        """The adapter should call cmd2.complete() and return its matches."""
        doc = Document(text="ex", cursor_position=2)
        completions = list(adapter.get_completions(doc))
        names = [c.text for c in completions]
        assert "exit" in names
        assert "exploit" in names
        assert "edit" not in names  # 'ex' doesn't match 'edit'

    def test_adapter_start_position_correct(self, shell, adapter):
        """start_position should be -len(word) so the prefix is replaced."""
        doc = Document(text="ex", cursor_position=2)
        completions = list(adapter.get_completions(doc))
        for c in completions:
            assert c.start_position == -2

    def test_adapter_with_leading_whitespace(self, shell, adapter):
        """Leading whitespace should not break the adapter."""
        doc = Document(text="  ex", cursor_position=4)
        completions = list(adapter.get_completions(doc))
        names = [c.text for c in completions]
        assert "exit" in names
        assert "exploit" in names

    def test_adapter_restores_readline(self, shell, adapter):
        """Readline functions must be restored after the adapter call."""
        import readline

        orig_lb = readline.get_line_buffer
        doc = Document(text="ex", cursor_position=2)
        list(adapter.get_completions(doc))
        assert readline.get_line_buffer is orig_lb
