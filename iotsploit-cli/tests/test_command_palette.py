"""Unit tests for the command palette catalog and completer.

These tests use a lightweight ``FakeShell`` stub so they can run without
Django initialization or a physical TTY.
"""

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from iotsploit_cli.command_palette import (
    Cmd2CompletionAdapter,
    CommandCatalog,
    CommandPaletteCompleter,
    CommandPaletteEntry,
    _sanitize_description,
)


# --------------------------------------------------------------------------- #
#  FakeShell stub
# --------------------------------------------------------------------------- #


class FakeShell:
    """Minimal shell stub mimicking cmd2.Cmd for catalog/completer tests."""

    def __init__(self):
        self._commands: list[str] = []
        self.hidden_commands: set[str] = set()
        self.disabled_commands: set[str] = set()
        self.aliases: dict = {}
        self.macros: dict = {}
        self.completion_matches: list = []
        self.display_matches: list = []

    def add_command(self, name: str, doc: str | None = None, category: str | None = None):
        def do_method(arg):  # noqa: ARG001
            pass

        do_method.__doc__ = doc
        if category:
            do_method.category = category
        setattr(self, "do_" + name, do_method)
        self._commands.append(name)

    def get_visible_commands(self):
        return [
            c
            for c in self._commands
            if c not in self.hidden_commands and c not in self.disabled_commands
        ]

    def get_command_doc(self, cmd_name: str) -> str:
        method = getattr(self, "do_" + cmd_name, None)
        if method and method.__doc__:
            return method.__doc__.split("\n")[0]
        return ""


def _make_default_shell() -> FakeShell:
    """Build a shell with representative commands."""
    shell = FakeShell()
    shell.add_command("edit", "Edit the current command line")
    shell.add_command("eof", "Internal sentinel")
    shell.add_command("exploit", "Execute all plugins in the IotSploit System")
    shell.add_command("exit", "Exit Console")
    shell.add_command("execute_plugin", "Execute a specific plugin", category="Plugin Commands")
    shell.add_command("help", "List available commands")
    shell.add_command("history", "View command history")
    shell.add_command("ls", "List directory contents")
    return shell


# --------------------------------------------------------------------------- #
#  _sanitize_description
# --------------------------------------------------------------------------- #


class TestSanitizeDescription:
    def test_normal_string(self):
        assert _sanitize_description("Execute a specific plugin") == "Execute a specific plugin"

    def test_none(self):
        assert _sanitize_description(None) == "No description available"

    def test_empty(self):
        assert _sanitize_description("") == "No description available"

    def test_whitespace_only(self):
        assert _sanitize_description("   ") == "No description available"

    def test_strips_ansi_escape(self):
        raw = "\x1b[31mExecute\x1b[0m \x1b[32mall\x1b[0m"
        assert _sanitize_description(raw) == "Execute all"

    def test_normalizes_whitespace(self):
        raw = "Execute   all\n\tplugins"
        assert _sanitize_description(raw) == "Execute all plugins"


# --------------------------------------------------------------------------- #
#  CommandCatalog
# --------------------------------------------------------------------------- #


class TestCommandCatalog:
    def test_includes_all_visible_e_commands(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "edit" in names
        assert "exploit" in names
        assert "exit" in names
        assert "execute_plugin" in names

    def test_excludes_eof_sentinel(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "eof" not in names

    def test_excludes_non_matching_prefixes(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "help" not in names
        assert "history" not in names
        assert "ls" not in names

    def test_h_prefix_returns_h_commands(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("h")
        names = [e.name for e in entries]
        assert "help" in names
        assert "history" in names
        assert "exit" not in names

    def test_excludes_hidden_commands(self):
        shell = _make_default_shell()
        shell.hidden_commands.add("exploit")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exploit" not in names

    def test_excludes_disabled_commands(self):
        shell = _make_default_shell()
        shell.disabled_commands.add("exit")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exit" not in names

    def test_excludes_aliases(self):
        shell = _make_default_shell()
        shell.aliases = {"exit_alias": "exit"}
        shell.add_command("exit_alias", "Alias for exit")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exit_alias" not in names

    def test_excludes_macros(self):
        shell = _make_default_shell()
        shell.macros = {"exit_macro": "exit"}
        shell.add_command("exit_macro", "Macro for exit")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        names = [e.name for e in entries]
        assert "exit_macro" not in names

    def test_description_uses_first_docstring_line(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        exploit_entry = next(e for e in entries if e.name == "exploit")
        assert exploit_entry.description == "Execute all plugins in the IotSploit System"

    def test_fallback_description_when_no_docstring(self):
        shell = FakeShell()
        shell.add_command("exploit", None)
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        entry = next(e for e in entries if e.name == "exploit")
        assert entry.description == "No description available"

    def test_description_strips_control_chars(self):
        shell = FakeShell()
        shell.add_command("exploit", "\x1b[31mExecute\x1b[0m all plugins")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        entry = next(e for e in entries if e.name == "exploit")
        assert "\x1b" not in entry.description
        assert entry.description == "Execute all plugins"

    def test_disabled_command_after_init_is_excluded(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        assert "exploit" in [e.name for e in catalog.get_eligible_entries("e")]
        shell.disabled_commands.add("exploit")
        assert "exploit" not in [e.name for e in catalog.get_eligible_entries("e")]

    def test_never_calls_do_handlers(self):
        shell = FakeShell()
        call_count = [0]

        def do_method(arg):  # noqa: ARG001
            call_count[0] += 1

        do_method.__doc__ = "Execute"
        setattr(shell, "do_exploit", do_method)
        shell._commands.append("exploit")

        catalog = CommandCatalog(shell)
        catalog.get_eligible_entries("e")
        assert call_count[0] == 0

    def test_exact_match_sorted_first(self):
        shell = FakeShell()
        shell.add_command("exploit", "Execute all")
        shell.add_command("edit", "Edit line")
        shell.add_command("e", "The exact match")
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        assert entries[0].name == "e"

    def test_case_insensitive_prefix(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        lower = catalog.get_eligible_entries("e")
        upper = catalog.get_eligible_entries("E")
        assert [e.name for e in lower] == [e.name for e in upper]

    def test_prefix_narrowing(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        all_e = set(e.name for e in catalog.get_eligible_entries("e"))
        ex_only = set(e.name for e in catalog.get_eligible_entries("ex"))
        assert ex_only.issubset(all_e)
        assert "exit" in ex_only
        assert "execute_plugin" in ex_only
        assert "edit" not in ex_only

    def test_empty_prefix_returns_empty(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        assert catalog.get_eligible_entries("") == []

    def test_category_is_captured(self):
        shell = _make_default_shell()
        catalog = CommandCatalog(shell)
        entries = catalog.get_eligible_entries("e")
        ep = next(e for e in entries if e.name == "execute_plugin")
        assert ep.category == "Plugin Commands"


# --------------------------------------------------------------------------- #
#  CommandCatalog.is_first_token_context
# --------------------------------------------------------------------------- #


class TestIsFirstTokenContext:
    def test_single_char(self):
        assert CommandCatalog.is_first_token_context("e", 1) is True

    def test_any_single_char(self):
        assert CommandCatalog.is_first_token_context("h", 1) is True

    def test_two_char_prefix(self):
        assert CommandCatalog.is_first_token_context("ex", 2) is True

    def test_cursor_in_middle_of_first_token(self):
        assert CommandCatalog.is_first_token_context("exploit", 3) is True

    def test_empty_text(self):
        assert CommandCatalog.is_first_token_context("", 0) is False

    def test_any_first_token_is_true(self):
        """Any non-empty first token activates the palette, not just 'e'."""
        assert CommandCatalog.is_first_token_context("help", 4) is True

    def test_cursor_in_argument(self):
        assert CommandCatalog.is_first_token_context("exploit extra", 9) is False

    def test_cursor_after_space(self):
        assert CommandCatalog.is_first_token_context("exploit ", 8) is False

    def test_uppercase_letter(self):
        assert CommandCatalog.is_first_token_context("E", 1) is True

    def test_leading_whitespace(self):
        assert CommandCatalog.is_first_token_context("  e", 3) is True


# --------------------------------------------------------------------------- #
#  CommandPaletteCompleter
# --------------------------------------------------------------------------- #


def _make_completer(shell=None):
    """Build a CommandPaletteCompleter with a FakeShell."""
    if shell is None:
        shell = _make_default_shell()
    catalog = CommandCatalog(shell)
    adapter = Cmd2CompletionAdapter(shell)
    return CommandPaletteCompleter(shell, catalog, adapter), shell


class TestCommandPaletteCompleter:
    def test_e_prefix_returns_all_eligible(self):
        completer, _ = _make_completer()
        doc = Document(text="e", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "edit" in names
        assert "exploit" in names
        assert "exit" in names
        assert "execute_plugin" in names
        assert "eof" not in names

    def test_h_prefix_returns_all_eligible(self):
        """Any prefix, not just 'e', activates the palette."""
        completer, _ = _make_completer()
        doc = Document(text="h", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "help" in names
        assert "history" in names

    def test_ex_narrows_results(self):
        completer, _ = _make_completer()
        doc = Document(text="ex", cursor_position=2)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "exit" in names
        assert "execute_plugin" in names
        assert "exploit" in names  # "exploit" starts with "ex"
        assert "edit" not in names

    def test_case_insensitive(self):
        completer, _ = _make_completer()
        doc = Document(text="E", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "edit" in names
        assert "exploit" in names

    def test_start_position_covers_first_token(self):
        completer, _ = _make_completer()
        doc = Document(text="ex", cursor_position=2)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        for comp in completer.get_completions(doc, event):
            assert comp.start_position == -2

    def test_leading_whitespace_handled(self):
        completer, _ = _make_completer()
        doc = Document(text="  e", cursor_position=3)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "edit" in names
        # start_position should be -1 (covers only the "e" character)
        for comp in completer.get_completions(doc, event):
            assert comp.start_position == -1

    def test_empty_input_no_results(self):
        completer, _ = _make_completer()
        doc = Document(text="", cursor_position=0)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert names == []

    def test_any_first_token_produces_results(self):
        """Typing any command prefix (not just 'e') produces palette results."""
        completer, _ = _make_completer()
        doc = Document(text="h", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert "help" in names
        assert "history" in names

    def test_text_after_space_no_palette_results(self):
        completer, _ = _make_completer()
        doc = Document(text="exploit extra", cursor_position=12)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert names == []

    def test_letter_inside_argument_no_results(self):
        completer, _ = _make_completer()
        doc = Document(text="help e", cursor_position=6)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        names = [c.text for c in completer.get_completions(doc, event)]
        assert names == []

    def test_display_meta_has_description(self):
        completer, _ = _make_completer()
        doc = Document(text="e", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        completions = list(completer.get_completions(doc, event))
        exploit_comp = next(c for c in completions if c.text == "exploit")
        meta = exploit_comp.display_meta
        meta_text = "".join(t[1] for t in meta) if isinstance(meta, list) else str(meta)
        assert "Execute all plugins" in meta_text

    def test_long_description_no_control_sequences(self):
        shell = FakeShell()
        shell.add_command("exploit", "\x1b[31m" + "A" * 200 + "\x1b[0m")
        catalog = CommandCatalog(shell)
        adapter = Cmd2CompletionAdapter(shell)
        completer = CommandPaletteCompleter(shell, catalog, adapter)
        doc = Document(text="e", cursor_position=1)
        event = CompleteEvent(text_inserted=True, completion_requested=False)
        for comp in completer.get_completions(doc, event):
            assert "\x1b" not in comp.text


# --------------------------------------------------------------------------- #
#  Cmd2CompletionAdapter
# --------------------------------------------------------------------------- #


class TestCmd2CompletionAdapter:
    def test_correctly_mocks_readline_and_returns_matches(self):
        """Verify the adapter sets readline mock and converts matches."""
        shell = FakeShell()
        captured = {}

        def fake_complete(text, state, custom_settings=None):
            if state == 0:
                import readline as rl

                captured["line"] = rl.get_line_buffer()
                captured["begidx"] = rl.get_begidx()
                captured["endidx"] = rl.get_endidx()
                shell.completion_matches = ["exploit", "exit"]
                shell.display_matches = ["Exploit all", "Exit"]
            try:
                return shell.completion_matches[state]
            except IndexError:
                return None

        shell.complete = fake_complete
        adapter = Cmd2CompletionAdapter(shell)
        doc = Document(text="ex", cursor_position=2)
        completions = list(adapter.get_completions(doc))

        assert captured["line"] == "ex"
        assert captured["begidx"] == 0
        assert captured["endidx"] == 2
        assert len(completions) == 2
        assert completions[0].text == "exploit"
        assert completions[0].start_position == -2
        assert completions[1].text == "exit"

    def test_word_in_second_position(self):
        """Verify begidx/endidx are correct for the second word."""
        shell = FakeShell()
        captured = {}

        def fake_complete(text, state, custom_settings=None):
            if state == 0:
                import readline as rl

                captured["begidx"] = rl.get_begidx()
                captured["endidx"] = rl.get_endidx()
                shell.completion_matches = ["foo"]
                shell.display_matches = ["foo"]
            try:
                return shell.completion_matches[state]
            except IndexError:
                return None

        shell.complete = fake_complete
        adapter = Cmd2CompletionAdapter(shell)
        doc = Document(text="exploit fo", cursor_position=10)
        list(adapter.get_completions(doc))

        assert captured["begidx"] == 8
        assert captured["endidx"] == 10

    def test_empty_word_returns_nothing(self):
        shell = FakeShell()
        shell.complete = lambda text, state, custom_settings=None: None
        adapter = Cmd2CompletionAdapter(shell)
        doc = Document(text="exploit ", cursor_position=8)
        completions = list(adapter.get_completions(doc))
        assert completions == []

    def test_handles_exception_gracefully(self):
        shell = FakeShell()

        def raising_complete(text, state, custom_settings=None):
            raise RuntimeError("boom")

        shell.complete = raising_complete
        adapter = Cmd2CompletionAdapter(shell)
        doc = Document(text="ex", cursor_position=2)
        completions = list(adapter.get_completions(doc))
        assert completions == []

    def test_restores_readline_after_use(self):
        """Verify readline originals are restored even on success."""
        import readline as rl

        orig_lb = rl.get_line_buffer
        shell = FakeShell()
        shell.completion_matches = ["test"]
        shell.display_matches = ["test"]
        adapter = Cmd2CompletionAdapter(shell)
        doc = Document(text="te", cursor_position=2)
        list(adapter.get_completions(doc))
        # After the call, readline should be restored
        assert rl.get_line_buffer is orig_lb


# --------------------------------------------------------------------------- #
#  CommandPaletteEntry
# --------------------------------------------------------------------------- #


class TestCommandPaletteEntry:
    def test_immutable(self):
        entry = CommandPaletteEntry(name="exploit", description="Execute all")
        with pytest.raises(AttributeError):
            entry.name = "changed"

    def test_defaults(self):
        entry = CommandPaletteEntry(name="test", description="desc")
        assert entry.category is None
