"""The one-line front end guesses, and says when it is guessing.

It exists because the full interface -- an adapter module, a registry entry, a
seed file -- is the right shape for a target worth keeping and far too much
for finding out whether a function you just wrote holds up. Everything it
infers is checked here, because a wrong guess is worse than no guess: it sends
the payload in a form the function never sees and reports nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from iotsploit_fuzzer.fuzz import infer_kind, load_target, resolve_exception

pytestmark = pytest.mark.unit


def takes_bytes(payload: bytes): ...
def takes_text(value: str): ...
def takes_path(path: Path): ...
def takes_named_path(filename): ...
def takes_mapping(data: Dict[str, Any]): ...
def takes_list(rows: List[int]): ...
def takes_anything(thing): ...


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        (takes_bytes, "bytes"),
        (takes_text, "text"),
        (takes_path, "file"),
        (takes_named_path, "file"),
        (takes_mapping, "json"),
        (takes_list, "json"),
        (takes_anything, "bytes"),
    ],
)
def test_the_input_kind_is_read_off_the_signature(function, expected):
    assert infer_kind(function) == expected


def test_a_mapping_is_not_mistaken_for_text():
    """``Dict[str, Any]`` contains "str", and checking for text first read
    every mapping as a string -- which sends JSON to a function expecting a
    dict and reports nothing at all."""
    assert infer_kind(takes_mapping) == "json"


def test_a_builtin_exception_needs_no_module():
    assert resolve_exception("ValueError", takes_bytes) == "builtins:ValueError"


def test_an_exception_is_found_beside_the_function_it_belongs_to():
    """Where a parser's own error class almost always lives."""
    from iotsploit_protocols.canbus.logfile import scan_log

    resolved = resolve_exception("CanLogError", scan_log)

    assert resolved == "iotsploit_protocols.canbus.logfile:CanLogError"


def test_an_exception_that_exists_nowhere_is_refused_by_name():
    with pytest.raises(SystemExit, match="NoSuchError"):
        resolve_exception("NoSuchError", takes_bytes)


def test_a_loose_file_can_be_named_by_path(tmp_path, monkeypatch):
    """So that fuzzing something you just wrote does not require installing it."""
    module = tmp_path / "loose_module.py"
    module.write_text("def parse(text):\n    return text\n")
    monkeypatch.setenv("PYTHONPATH", "")

    function, dotted = load_target(f"{module}:parse")

    assert dotted == "loose_module:parse"
    assert function("x") == "x"
