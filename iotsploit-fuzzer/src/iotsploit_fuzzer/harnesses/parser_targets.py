"""What a parse target is, and the registry applications add theirs to.

This module knows nothing about any particular application. It defines the
shape of a target -- the callable to reach, the exceptions its own docstring
declares, and the budget one parse gets -- and the helpers an adapter needs to
turn a fuzzer's bytes into that callable's arguments.

The targets themselves live in a **pack**: an ordinary module that imports
:func:`register` and calls it. IoTSploit's own pack is
:mod:`iotsploit_fuzzer.targets.iotsploit`; another application writes its own
and names it with ``--targets``, needing nothing from this package but this
file.

An adapter is one function taking ``bytes`` and calling the thing under test.
It raises :class:`Skip` when it cannot build an input at all, which is not a
result and is never recorded -- otherwise "this payload was not valid JSON"
would fill the corpus. Adapters are resolved *inside the worker subprocess*,
by dotted path, so nothing here has to be picklable and a target that dies
takes only the worker with it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Tuple


class Skip(Exception):
    """This payload does not form an input for this target."""


class MetamorphicError(Exception):
    """A relation between two calls broke, without either call raising.

    The only class of defect that a crash-only oracle cannot see, and the one
    that matters most on a live bus: a silently wrong value.
    """


@dataclass(frozen=True)
class ParseTarget:
    """One parse surface, with the budget and the contract it is held to."""

    name: str
    #: ``module:function`` taking ``bytes`` and returning the parsed value.
    adapter: str
    #: ``module:ExceptionName`` for every exception the contract declares.
    #: An empty tuple means the contract is "never raises".
    declared: Tuple[str, ...] = ()
    seeds: Tuple[bytes, ...] = ()
    budget_seconds: float = 5.0
    memory_mb: int = 768
    output_kb: int = 256
    payload_max_bytes: int = 1 << 20
    #: Bumped by hand when an adapter's translation changes. Part of the
    #: fingerprint, so bumping it forces a ledger re-baseline rather than
    #: reporting every entry as a boundary movement.
    adapter_version: str = "1"

    @property
    def fingerprint(self) -> str:
        """Identity of the oracle, not of the target.

        A ledger recorded under one fingerprint cannot be diffed against a
        campaign run under another: changing the declared set moves the
        accept/reject line by definition, and every entry would read as a
        boundary movement that nobody caused.
        """
        from ..analysis.outcome import OUTCOME_VERSION

        material = "\x00".join(
            (self.adapter, self.adapter_version, str(OUTCOME_VERSION), *sorted(self.declared))
        )
        return hashlib.sha256(material.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# The registry a pack fills
# --------------------------------------------------------------------------

REGISTRY: Dict[str, ParseTarget] = {}


def register(target: ParseTarget) -> ParseTarget:
    """Add a target to the registry, replacing any entry of the same name."""
    REGISTRY[target.name] = target
    return target


# --------------------------------------------------------------------------
# Helpers a pack's adapters can use
# --------------------------------------------------------------------------


def temp_file(payload: bytes, suffix: str) -> str:
    """Write a payload down for a target that wants a path, not bytes.

    The caller unlinks it. Worth doing in a ``finally``: the worker is killed
    without warning often enough that anything else leaks.
    """
    handle, path = tempfile.mkstemp(suffix=suffix, prefix="fuzz_")
    with os.fdopen(handle, "wb") as fh:
        fh.write(payload)
    return path


def json_input(payload: bytes) -> Any:
    """Decode a payload as JSON, or skip it.

    ``ValueError`` covers ``JSONDecodeError`` and the 4300-digit int-string
    limit, which fails inside ``int()`` rather than in the scanner.
    ``RecursionError`` covers a document nested past the interpreter's limit:
    the stack ran out inside ``json``, before any code under test was reached,
    and reporting that as a violation would blame the target for the adapter's
    own translation step.
    """
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise Skip(str(error)) from None
    except RecursionError as error:
        raise Skip(str(error)) from None


def json_object(payload: bytes, what: str = "an object") -> Dict[str, Any]:
    """:func:`json_input`, refusing anything that is not a JSON object."""
    raw = json_input(payload)
    if not isinstance(raw, dict):
        raise Skip(f"expected {what}, got {type(raw).__name__}")
    return raw


def text_input(payload: bytes) -> str:
    """Decode a payload as UTF-8 text, or skip it."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Skip(str(error)) from None
