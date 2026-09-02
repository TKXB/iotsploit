"""Declared bool parameters arrive as bools, whatever the transport sent."""

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


def test_undeclared_and_non_bool_parameters_are_passed_through_untouched():
    original = {'label': 'false', 'count': '3', 'undeclared': 'no'}

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
