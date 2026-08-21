#!/usr/bin/env python
"""
Console adapter for the plugin interaction port.

The CLI runs plugins in-process, so a prompt is answered right here on the
terminal: nothing is persisted, no execution record exists, and no transport is
involved. This adapter is what keeps an interactive plugin usable from the
shell, and what a future single-process mode would use instead of a broker.
"""

from __future__ import annotations

import asyncio
from typing import Any

from cmd2 import ansi

from iotsploit_core.ports.interaction import (
    InteractionCancelled,
    InteractionInvalid,
    Prompt,
    PromptSugar,
    coerce_answer,
    guard_sync_call,
)
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class ConsoleInteractionAdapter(PromptSugar):
    """Ask on stdin, answer immediately.

    ``timeout`` is accepted and ignored: a terminal prompt has an operator
    sitting in front of it, and there is no broker to expire the request.
    Ctrl-C and EOF both mean cancel.
    """

    def __init__(self, stdin=None, stdout=None):
        self._stdin = stdin
        self._stdout = stdout
        #: Title and description of the last prompt written, so a plugin that
        #: asks the same question in a loop does not reprint its own preamble
        #: between every answer. A REPL-shaped plugin asks once per request,
        #: and three lines of unchanged boilerplate per request buries the
        #: transcript it is there to produce.
        self._last_header: tuple[str, str | None] | None = None

    # -- port ------------------------------------------------------------
    def request(self, prompt: Prompt) -> Any:
        guard_sync_call("request")
        return self._ask(prompt)

    async def arequest(self, prompt: Prompt) -> Any:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._ask, prompt
        )

    def check_cancelled(self) -> None:
        """No-op: the operator has Ctrl-C."""

    async def acheck_cancelled(self) -> None:
        """No-op: the operator has Ctrl-C."""

    # -- internals -------------------------------------------------------
    def _write(self, text: str = "") -> None:
        if self._stdout is not None:
            self._stdout.write(text + "\n")
        else:
            print(text)

    def _read(self, prompt_text: str) -> str:
        if self._stdin is not None:
            self._write(prompt_text)
            line = self._stdin.readline()
            if line == "":
                raise EOFError
            return line.rstrip("\n")
        return input(prompt_text)

    def _ask(self, prompt: Prompt) -> Any:
        header = (prompt.title, prompt.description)
        if header != self._last_header:
            self._write()
            self._write(ansi.style(prompt.title, bold=True))
            if prompt.description:
                self._write(ansi.style(prompt.description, fg=ansi.Fg.LIGHT_GRAY))
        self._last_header = header

        if prompt.kind in ("single_choice", "multiple_choice"):
            for index, choice in enumerate(prompt.choices, start=1):
                self._write(f"  {index}. {choice.display}")

        while True:
            try:
                raw = self._read(ansi.style(self._input_label(prompt), fg=ansi.Fg.YELLOW))
            except (EOFError, KeyboardInterrupt):
                self._write()
                raise InteractionCancelled(
                    f"Cancelled at the prompt: {prompt.title}"
                ) from None

            try:
                return coerce_answer(prompt, self._parse(prompt, raw))
            except InteractionInvalid as exc:
                self._write(ansi.style(str(exc), fg=ansi.Fg.RED))

    @staticmethod
    def _input_label(prompt: Prompt) -> str:
        if prompt.kind == "confirm":
            return f"{prompt.confirm_label} [y/N]: "
        if prompt.kind == "multiple_choice":
            return "Numbers, comma separated: "
        if prompt.kind == "single_choice":
            return "Number: "
        if prompt.default is not None:
            return f"Value [{prompt.default}]: "
        return "Value: "

    @staticmethod
    def _parse(prompt: Prompt, raw: str) -> Any:
        """Turn terminal text into the shape ``coerce_answer`` expects."""
        raw = raw.strip()

        if raw == "" and prompt.default is not None:
            return prompt.default

        if prompt.kind == "confirm":
            if raw.lower() in ("y", "yes"):
                return True
            if raw.lower() in ("n", "no", ""):
                return False
            raise InteractionInvalid("Answer y or n.")

        if prompt.kind == "single_choice":
            return prompt.choice_values[_index(raw, len(prompt.choices))]

        if prompt.kind == "multiple_choice":
            if raw == "":
                return []
            parts = [p for p in (part.strip() for part in raw.split(",")) if p]
            return [
                prompt.choice_values[_index(part, len(prompt.choices))]
                for part in parts
            ]

        return raw


def _index(token: str, count: int) -> int:
    """One-based selection token to a zero-based index."""
    try:
        number = int(token)
    except ValueError:
        raise InteractionInvalid(f"{token!r} is not a number.") from None
    if not 1 <= number <= count:
        raise InteractionInvalid(f"Pick a number between 1 and {count}.")
    return number - 1
