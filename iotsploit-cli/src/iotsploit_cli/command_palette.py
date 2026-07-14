"""Command palette for IoTSploit CLI -- live command discovery.

This module implements the live prompt-toolkit command palette that shows
eligible commands as the user types at the top-level interactive prompt.
Any typed prefix triggers the palette; additional characters filter the list
in real time.  It preserves all existing cmd2 behaviour for non-TTY input,
nested prompts, scripts, and argument completion.

The public classes are:

* :class:`CommandPaletteEntry`       -- immutable metadata value
* :class:`CommandCatalog`            -- UI-independent metadata provider
* :class:`Cmd2CompletionAdapter`     -- bridges cmd2 readline Tab completion
* :class:`CommandPaletteCompleter`   -- prompt-toolkit ``Completer``
* :class:`PaletteInputSession`       -- prompt-toolkit ``PromptSession`` wrapper

This module must **not** import anything from ``iotsploit_cli.console`` or
Django so it can be unit-tested in isolation.
"""

import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import (
    Completion,
    CompleteEvent,
    Completer,
)
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory

# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #

FALLBACK_DESCRIPTION = "No description available"
EOF_SENTINEL = "eof"

# Matches ANSI/CSI escape sequences so descriptions are control-char free.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #


def _sanitize_description(raw: Optional[str]) -> str:
    """Strip ANSI control characters and normalise whitespace."""
    if not raw:
        return FALLBACK_DESCRIPTION
    cleaned = _ANSI_ESCAPE_RE.sub("", raw)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return FALLBACK_DESCRIPTION
    return cleaned


# --------------------------------------------------------------------------- #
#  CommandPaletteEntry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CommandPaletteEntry:
    """Immutable value describing a single palette entry."""

    name: str
    description: str
    category: Optional[str] = None


# --------------------------------------------------------------------------- #
#  CommandCatalog  (UI-independent metadata provider)
# --------------------------------------------------------------------------- #


class CommandCatalog:
    """UI-independent command metadata provider for the command palette.

    The catalog reads metadata **only** -- it never calls a ``do_*`` handler.
    """

    def __init__(self, shell: Any) -> None:
        """Store a reference to the shell; do not invoke handlers."""
        self._shell = shell

    # -- public API -------------------------------------------------------- #

    def get_eligible_entries(self, prefix: str) -> List[CommandPaletteEntry]:
        """Return eligible palette entries whose name starts with *prefix*.

        Matching is case-insensitive.  Results are sorted with exact matches
        first, then alphabetical.
        """
        if not prefix:
            return []
        prefix_lower = prefix.lower()
        entries: List[CommandPaletteEntry] = []

        try:
            visible = self._shell.get_visible_commands()
        except Exception:
            return []

        # Build exclusion sets for aliases, macros, and the eof sentinel.
        aliases: set = set()
        macros: set = set()
        if hasattr(self._shell, "aliases") and self._shell.aliases:
            aliases = set(self._shell.aliases.keys())
        if hasattr(self._shell, "macros") and self._shell.macros:
            macros = set(self._shell.macros.keys())

        for cmd_name in visible:
            # Prefix filter (case-insensitive)
            if not cmd_name.lower().startswith(prefix_lower):
                continue
            # Exclude eof sentinel
            if cmd_name == EOF_SENTINEL:
                continue
            # Exclude aliases and macros (MVP: no stable description metadata)
            if cmd_name in aliases or cmd_name in macros:
                continue

            # Description via the shell's existing doc extractor
            try:
                raw_doc = self._shell.get_command_doc(cmd_name)
            except Exception:
                raw_doc = None
            description = _sanitize_description(raw_doc)

            # Optional category from cmd2's @with_category decorator
            category: Optional[str] = None
            cmd_func = getattr(self._shell, "do_" + cmd_name, None)
            if cmd_func is not None and hasattr(cmd_func, "category"):
                category = cmd_func.category

            entries.append(
                CommandPaletteEntry(
                    name=cmd_name,
                    description=description,
                    category=category,
                )
            )

        # Sort: exact match first, then alphabetical by name
        entries.sort(
            key=lambda e: (e.name.lower() != prefix_lower, e.name.lower())
        )
        return entries

    @staticmethod
    def is_first_token_context(text: str, cursor_pos: int) -> bool:
        """Return ``True`` if the cursor is in the first token and it is non-empty.

        Leading whitespace is skipped so that ``  he`` is recognised the same
        as ``he``.  This activates the palette for any command prefix, not just
        a specific letter.
        """
        stripped = text.lstrip()
        if not stripped:
            return False
        offset = len(text) - len(stripped)
        first_space = stripped.find(" ")
        if first_space == -1:
            in_first_token = True
            first_word = stripped
        else:
            rel_cursor = cursor_pos - offset
            in_first_token = rel_cursor <= first_space
            first_word = stripped[:first_space]

        if not in_first_token:
            return False
        if not first_word:
            return False
        return True


# --------------------------------------------------------------------------- #
#  Cmd2CompletionAdapter  (bridges cmd2 readline Tab completion)
# --------------------------------------------------------------------------- #


class Cmd2CompletionAdapter:
    """Bridge cmd2's readline-based ``complete()`` to prompt-toolkit.

    When the user presses **Tab** outside the first-token context (i.e.
    for argument completion), this adapter temporarily mocks the ``readline``
    module functions that cmd2 reads and calls ``shell.complete(text, 0)`` to
    populate ``completion_matches`` / ``display_matches``.
    """

    def __init__(self, shell: Any) -> None:
        self._shell = shell

    def get_completions(self, document: Document) -> Iterable[Completion]:
        """Delegate to cmd2's ``complete()`` and yield prompt-toolkit Completions."""
        try:
            from cmd2 import rl_utils

            readline_mod = rl_utils.readline
        except (ImportError, AttributeError):
            return

        line = document.text
        cursor = document.cursor_position

        # Find the current word being completed (scan backwards for whitespace)
        word_start = cursor
        while word_start > 0 and not line[word_start - 1].isspace():
            word_start -= 1
        text = line[word_start:cursor]

        if not text:
            return

        # Save originals
        orig_get_line_buffer = readline_mod.get_line_buffer
        orig_get_begidx = readline_mod.get_begidx
        orig_get_endidx = readline_mod.get_endidx

        try:
            # Mock readline functions so cmd2's complete() sees the PT Document
            readline_mod.get_line_buffer = lambda: line
            readline_mod.get_begidx = lambda: word_start
            readline_mod.get_endidx = lambda: cursor

            # state=0 triggers _reset_completion_defaults + _perform_completion
            self._shell.complete(text, 0)

            matches = getattr(self._shell, "completion_matches", [])
            displays = getattr(self._shell, "display_matches", matches)

            for i, match in enumerate(matches):
                display = displays[i] if i < len(displays) else match
                yield Completion(
                    match,
                    start_position=-len(text),
                    display=display,
                )
        except Exception:
            return
        finally:
            # Always restore originals
            readline_mod.get_line_buffer = orig_get_line_buffer
            readline_mod.get_begidx = orig_get_begidx
            readline_mod.get_endidx = orig_get_endidx


# --------------------------------------------------------------------------- #
#  CommandPaletteCompleter  (prompt-toolkit Completer)
# --------------------------------------------------------------------------- #


class CommandPaletteCompleter(Completer):
    """prompt-toolkit ``Completer`` for live command palette and cmd2 Tab delegation.

    * While the cursor is in the first token and it is non-empty, yield live
      palette entries for any command prefix (works with
      ``complete_while_typing=True``).
    * When **Tab** is explicitly requested outside the first token (i.e.
      for argument completion), delegate to :class:`Cmd2CompletionAdapter`
      so existing cmd2 argument completion still works.
    """

    def __init__(
        self,
        shell: Any,
        catalog: CommandCatalog,
        cmd2_adapter: Cmd2CompletionAdapter,
    ) -> None:
        self._shell = shell
        self._catalog = catalog
        self._adapter = cmd2_adapter

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        cursor = document.cursor_position

        # Strip leading whitespace for token analysis
        stripped = text.lstrip()
        offset = len(text) - len(stripped)
        first_space = stripped.find(" ")
        if first_space == -1:
            in_first_token = True
            first_word = stripped
        else:
            rel_cursor = cursor - offset
            in_first_token = rel_cursor <= first_space
            first_word = stripped[:first_space]

        # -- live palette for any first-token prefix ---------------------- #
        if in_first_token and first_word:
            for entry in self._catalog.get_eligible_entries(first_word):
                yield Completion(
                    entry.name,
                    start_position=-len(first_word),
                    display=entry.name,
                    display_meta=entry.description,
                )
        # -- explicit Tab delegation (argument completion) ---------------- #
        elif complete_event.completion_requested:
            yield from self._adapter.get_completions(document)


# --------------------------------------------------------------------------- #
#  PaletteInputSession  (prompt-toolkit PromptSession wrapper)
# --------------------------------------------------------------------------- #


class PaletteInputSession:
    """Wrap a prompt-toolkit ``PromptSession`` for the command palette.

    Most key behaviour (Up/Down navigation, Tab apply, Enter accept, Escape
    dismiss) is provided by prompt-toolkit's defaults when
    ``complete_while_typing=True`` with ``CompleteStyle.COLUMN``.
    """

    def __init__(self, shell: Any, completer: CommandPaletteCompleter) -> None:
        self._shell = shell
        self._session: PromptSession = PromptSession(
            completer=completer,
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            history=InMemoryHistory(),
        )

    def prompt(self, prompt_text: str) -> str:
        """Display the prompt and return the accepted line.

        Raises:
            KeyboardInterrupt: when the user presses Ctrl+C.
            Returns ``'eof'`` on EOF (Ctrl+D on empty line), matching cmd2.
        """
        message = ANSI(prompt_text) if prompt_text else ""
        try:
            line = self._session.prompt(message=message)
            return line
        except KeyboardInterrupt:
            raise
        except EOFError:
            return EOF_SENTINEL
