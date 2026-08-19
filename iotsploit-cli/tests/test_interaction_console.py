"""The CLI answers prompts on the terminal.

This is what keeps an interactive plugin usable from the shell: the CLI runs
plugins in-process, so there is no broker to route a question through.
"""

from __future__ import annotations

import io

import pytest

from iotsploit_cli.interaction_console import ConsoleInteractionAdapter
from iotsploit_core.ports.interaction import (
    InteractionCancelled,
    Prompt,
)

pytestmark = pytest.mark.unit


def adapter(script: str) -> tuple[ConsoleInteractionAdapter, io.StringIO]:
    out = io.StringIO()
    return ConsoleInteractionAdapter(stdin=io.StringIO(script), stdout=out), out


def test_confirm_reads_yes():
    port, _ = adapter("y\n")
    assert port.request(Prompt(kind="confirm", title="Reset the ECU?")) is True


def test_confirm_treats_anything_else_as_no():
    port, _ = adapter("n\n")
    assert port.request(Prompt(kind="confirm", title="Reset the ECU?")) is False


def test_single_choice_is_answered_by_number():
    port, out = adapter("2\n")
    prompt = Prompt(kind="single_choice", title="Session",
                    choices=["default", "extended", "programming"])
    assert port.request(prompt) == "extended"
    assert "1. default" in out.getvalue()
    assert "2. extended" in out.getvalue()


def test_multiple_choice_takes_a_comma_list():
    port, _ = adapter("1,3\n")
    prompt = Prompt(kind="multiple_choice", title="ECUs",
                    choices=["gw", "bcm", "ivi"])
    assert port.request(prompt) == ["gw", "ivi"]


def test_empty_input_takes_the_default():
    port, _ = adapter("\n")
    prompt = Prompt(kind="single_choice", title="Session",
                    choices=["default", "extended"], default="extended")
    assert port.request(prompt) == "extended"


def test_integer_reprompts_until_it_is_in_range():
    port, out = adapter("9000\n512\n")
    prompt = Prompt(kind="integer", title="DIDs", min_value=1, max_value=4096)
    assert port.request(prompt) == 512
    assert "at most 4096" in out.getvalue()


def test_out_of_range_selection_reprompts():
    port, out = adapter("7\n1\n")
    prompt = Prompt(kind="single_choice", title="Session", choices=["default"])
    assert port.request(prompt) == "default"
    assert "between 1 and 1" in out.getvalue()


def test_non_numeric_selection_reprompts():
    port, out = adapter("abc\n1\n")
    prompt = Prompt(kind="single_choice", title="Session", choices=["default"])
    assert port.request(prompt) == "default"
    assert "not a number" in out.getvalue()


def test_eof_cancels_the_run():
    port, _ = adapter("")
    with pytest.raises(InteractionCancelled):
        port.request(Prompt(kind="text", title="Label"))


def test_description_is_shown():
    port, out = adapter("y\n")
    port.request(Prompt(kind="confirm", title="Reset?",
                        description="Drops off the bus for 4s."))
    assert "Drops off the bus" in out.getvalue()


def test_check_cancelled_is_a_no_op():
    port, _ = adapter("")
    assert port.check_cancelled() is None
