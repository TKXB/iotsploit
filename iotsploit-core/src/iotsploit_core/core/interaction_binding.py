"""
Execution-scoped binding for the interaction port.

Plugin instances are cached and reused, and backend context is injected once
per instance behind ``_iots_ctx_injected``. Storing an interaction port on the
injected ``PluginContext`` would therefore pin the first execution's identity
forever. The port is bound per execution here instead, and
``PluginContext.interaction`` resolves it lazily on every call.

This is service location rather than injection -- a deliberate deviation, taken
because the plan forbids changing the ``execute(target, parameters)`` signature.
It is kept contained: one module, set in one place.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

_current_interaction: ContextVar[Optional[Any]] = ContextVar(
    "iotsploit_interaction", default=None
)


@contextmanager
def bind_interaction(port: Optional[Any]) -> Iterator[Optional[Any]]:
    """Bind ``port`` for the duration of the block.

    Note for plugin authors: context variables do not propagate into threads
    started with ``threading.Thread``. A plugin that prompts from a thread it
    spawned must capture ``ctx.interaction`` first and pass the object in.
    """
    token = _current_interaction.set(port)
    try:
        yield port
    finally:
        _current_interaction.reset(token)


def current_interaction() -> Optional[Any]:
    """The port bound to the running execution, or ``None``."""
    return _current_interaction.get()
