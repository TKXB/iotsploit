"""A declared parameter arrives as its declared type, whatever the transport sent.

Parameters come from the web and CLI layers as JSON strings. `bool("false")`
is True, so an opt-in sent as text silently turned on; and a plugin declaring
`'type': 'int'` was handed `"3"` and had to parse it itself, which four
plugins did with a byte-identical helper and twelve did not do at all. The
boundary that hands parameters over owns both.
"""

from __future__ import annotations

import pytest

from iotsploit_core.core.base_plugin import BasePlugin
from iotsploit_core.core.exploit_manager import ExploitPluginManager
from iotsploit_core.utils import as_bool

pytestmark = pytest.mark.unit


class DeclaringPlugin(BasePlugin):
    def __init__(self):
        super().__init__({
            'Name': 'Declaring Plugin',
            'Parameters': {
                'opt_in': {'type': 'bool', 'default': False},
                'label': {'type': 'str', 'default': ''},
                'count': {'type': 'int', 'default': 1},
                'address': {'type': 'int', 'min': 0, 'max': 0xFFFF},
                'ratio': {'type': 'float'},
            },
        })


coerce = ExploitPluginManager._coerce_parameters


@pytest.mark.parametrize(
    ("sent", "expected"),
    [("false", False), ("False", False), ("no", False), ("n", False), ("off", False), ("0", False),
     ("true", True), ("yes", True), ("y", True), ("on", True), ("1", True),
     (True, True), (False, False)],
)
def test_declared_bools_survive_the_string_transport(sent, expected):
    """bool("false") is True, which silently inverted every opt-in sent as text."""
    coerced = coerce(DeclaringPlugin(), {'opt_in': sent})

    assert coerced['opt_in'] is expected


@pytest.mark.parametrize(
    ("sent", "expected"),
    [("3", 3), (3, 3), ("0x1000", 4096), ("  7 ", 7)],
)
def test_a_declared_int_is_an_int_or_a_clean_error_but_never_a_string(sent, expected):
    """Base 0, because the address and identifier fields these carry are
    habitually written in hex."""
    coerced = coerce(DeclaringPlugin(), {'count': sent})

    assert coerced['count'] == expected


def test_a_declared_float_survives_the_string_transport():
    assert coerce(DeclaringPlugin(), {'ratio': '2.5'})['ratio'] == 2.5


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({'count': 'abc'}, 'count must be an integer'),
        ({'address': '70000'}, 'address must be between 0 and 65535'),
        ({'address': ''}, 'address is required'),
    ],
)
def test_a_number_that_is_not_one_is_refused_by_name(parameters, message):
    """The range lives with the declaration. That is what let the four
    duplicate `_integer` helpers be deleted rather than merely shortened."""
    with pytest.raises(ValueError, match=message):
        coerce(DeclaringPlugin(), parameters)


@pytest.mark.parametrize(
    ("sent", "expected"),
    [("3", 3), ("0x10", 16), ("  7 ", 7), (3, 3), (2.0, 2)],
)
def test_a_declared_int_accepts_whole_numbers_however_they_arrive(sent, expected):
    assert coerce(DeclaringPlugin(), {'count': sent})['count'] == expected


@pytest.mark.parametrize(
    ("sent", "message"),
    [
        (1.5, "whole number"),
        (True, "must be an integer"),
        (False, "must be an integer"),
        ("1.5", "must be an integer"),
    ],
)
def test_a_declared_int_refuses_what_it_would_have_to_round_or_reinterpret(sent, message):
    """Found by fuzzing the schema alongside the parameters. ``int(1.5)`` is
    1 and ``int(True)`` is 1, so a declared int used to accept both and the
    caller never learned the value had changed. For a port or an address
    that is a number nobody wrote."""
    with pytest.raises(ValueError, match=message):
        coerce(DeclaringPlugin(), {'count': sent})


def test_a_declared_float_is_not_a_place_to_put_a_bool():
    with pytest.raises(ValueError, match="must be a number"):
        coerce(DeclaringPlugin(), {'ratio': True})


def test_a_schema_declaring_a_non_numeric_bound_is_refused_not_crashed_on():
    """Found by fuzzing the schema alongside the parameters. The bounds are
    written by hand by a plugin author, so ``"min": "0"`` is as likely as
    ``"min": 0`` -- and comparing a str with an int raised a TypeError that
    this boundary does not declare, on every call to that plugin."""
    class BadBound(BasePlugin):
        def __init__(self):
            super().__init__({'Parameters': {'port': {'type': 'int', 'min': '0'}}})

    with pytest.raises(ValueError, match="non-numeric min"):
        coerce(BadBound(), {'port': '5'})


def test_undeclared_and_string_parameters_are_passed_through_untouched():
    original = {'label': 'false', 'undeclared': 'no'}

    coerced = coerce(DeclaringPlugin(), dict(original))

    assert coerced == original


def test_absent_parameters_are_not_invented():
    coerced = coerce(DeclaringPlugin(), {'label': 'x'})

    assert 'opt_in' not in coerced


def test_a_plugin_without_a_schema_is_left_alone():
    assert coerce(object(), {'opt_in': 'false'}) == {'opt_in': 'false'}
    assert coerce(DeclaringPlugin(), None) is None


def test_as_bool_falls_back_to_truthiness_for_anything_else():
    assert as_bool([]) is False
    assert as_bool(['x']) is True
    assert as_bool(2) is True
