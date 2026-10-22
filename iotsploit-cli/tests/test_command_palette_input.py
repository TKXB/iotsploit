"""Integration tests for the command palette using prompt-toolkit PipeInput.

These tests use ``create_pipe_input`` and ``DummyOutput`` so they are
deterministic and require no physical TTY.
"""

from prompt_toolkit import PromptSession as PTSession
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from iotsploit_cli.command_palette import (
    Cmd2CompletionAdapter,
    CommandCatalog,
    CommandPaletteCompleter,
    EOF_SENTINEL,
    PaletteInputSession,
)


# --------------------------------------------------------------------------- #
#  FakeShell stub (shared with unit tests)
# --------------------------------------------------------------------------- #


class FakeShell:
    """Minimal shell stub mimicking cmd2.Cmd for palette tests."""

    def __init__(self):
        self._commands: list[str] = []
        self.hidden_commands: set[str] = set()
        self.disabled_commands: set[str] = set()
        self.aliases: dict = {}
        self.macros: dict = {}

    def add_command(self, name: str, doc: str | None = None):
        def do_method(arg):  # noqa: ARG001
            pass

        do_method.__doc__ = doc
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


def _make_palette(shell=None, inp=None):
    """Build a PaletteInputSession with a FakeShell and patched PT session."""
    if shell is None:
        shell = FakeShell()
        shell.add_command("edit", "Edit the current command line")
        shell.add_command("exploit", "Execute all plugins in the IotSploit System")
        shell.add_command("exit", "Exit Console")
        shell.add_command("execute_plugin", "Execute a specific plugin")
        shell.add_command("help", "List available commands")
    catalog = CommandCatalog(shell)
    adapter = Cmd2CompletionAdapter(shell)
    completer = CommandPaletteCompleter(shell, catalog, adapter)
    session = PaletteInputSession(shell, completer, input=inp, output=DummyOutput())
    return session, shell, completer


def _patch_session_with_pipe(session: PaletteInputSession, inp, completer):
    """Rebuild the inner session on the pipe.

    Kept because each test opens its own pipe after building the palette. It no
    longer rescues a session built against the real terminal -- _make_palette is
    given the pipe up front, since on Windows constructing the default output
    raises NoConsoleScreenBufferError before this could run.
    """
    session._session = PTSession(
        input=inp,
        output=DummyOutput(),
        completer=completer,
        complete_while_typing=True,
    )


# --------------------------------------------------------------------------- #
#  Integration tests
# --------------------------------------------------------------------------- #


class TestPaletteInputAcceptance:
    """Tests that the palette session accepts and returns text."""

    def test_typing_exit_returns_exit(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("exit\r")
            result = session.prompt("test> ")
            assert result == "exit"

    def test_empty_enter_returns_empty(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("\r")
            result = session.prompt("test> ")
            assert result == ""

    def test_ctrl_d_returns_eof_sentinel(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("\x04")  # Ctrl+D = EOT
            result = session.prompt("test> ")
            assert result == EOF_SENTINEL

    def test_zero_matches_literal_submission(self):
        """Enter with no completion matches submits the literal text."""
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("zzz\r")
            result = session.prompt("test> ")
            assert result == "zzz"


class TestPaletteAnsiPrompt:
    """Tests that ANSI-styled prompts are handled correctly."""

    def test_ansi_prompt_not_literal_escape(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("help\r")
            # The ANSI prompt should not become literal escape text
            result = session.prompt("\x1b[34m<IoX_SHELL> \x1b[0m")
            assert result == "help"
            # Verify the result doesn't contain escape sequences
            assert "\x1b" not in result

    def test_plain_prompt_works(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("exit\r")
            result = session.prompt("simple> ")
            assert result == "exit"


class TestPaletteCompleterIntegration:
    """Tests that the completer is wired correctly in the session."""

    def test_command_completes_to_exit(self):
        """Typing 'exit' + Enter returns 'exit' through the full PT session."""
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("exit\r")
            result = session.prompt("test> ")
            assert result == "exit"

    def test_any_command_submitted_correctly(self):
        """Any command, not just e-prefix, is submitted correctly."""
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("help\r")
            result = session.prompt("test> ")
            assert result == "help"

    def test_exploit_full_typing(self):
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("exploit\r")
            result = session.prompt("test> ")
            assert result == "exploit"

    def test_multiline_argument_accepted(self):
        """Text after a command name is submitted correctly."""
        session, _, completer = _make_palette()
        with create_pipe_input() as inp:
            _patch_session_with_pipe(session, inp, completer)
            inp.send_text("exploit some_arg\r")
            result = session.prompt("test> ")
            assert result == "exploit some_arg"


class TestPaletteSessionCreation:
    """Tests for PaletteInputSession construction."""

    def test_can_be_created(self):
        session, _, _ = _make_palette()
        assert session is not None
        assert session._session is not None

    def test_has_completer(self):
        session, _, completer = _make_palette()
        assert session._session.completer is completer
