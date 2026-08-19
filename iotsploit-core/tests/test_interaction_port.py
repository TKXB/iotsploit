"""Typed prompt construction, answer coercion, and the execution-scoped binding.

The binding tests are the important ones. Plugin instances are cached and
backend context is injected once per instance, so a port stored on the context
would outlive the execution that created it -- these pin the behaviour that
prevents prompts reaching a finished run.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from iotsploit_core.context import PluginContext
from iotsploit_core.core.interaction_binding import bind_interaction, current_interaction
from iotsploit_core.ports.interaction import (
    Choice,
    InteractionInvalid,
    InteractionUnavailable,
    Prompt,
    PromptSugar,
    coerce_answer,
    guard_sync_call,
)

pytestmark = pytest.mark.unit


class RecordingPort(PromptSugar):
    """Answers with a canned value and remembers what it was asked."""

    def __init__(self, answer=None):
        self.answer = answer
        self.prompts: list[Prompt] = []

    def request(self, prompt: Prompt):
        self.prompts.append(prompt)
        return coerce_answer(prompt, self.answer)

    async def arequest(self, prompt: Prompt):
        return self.request(prompt)

    def check_cancelled(self) -> None:
        pass

    async def acheck_cancelled(self) -> None:
        pass


# ── Prompt construction ──────────────────────────────────────────────

def test_unknown_kind_is_a_plugin_bug():
    with pytest.raises(InteractionInvalid, match="Unknown prompt kind"):
        Prompt(kind="secret", title="Key")


def test_choice_prompt_needs_choices():
    with pytest.raises(InteractionInvalid, match="at least one choice"):
        Prompt(kind="single_choice", title="Session")


def test_choices_accept_strings_pairs_and_objects():
    prompt = Prompt(
        kind="single_choice",
        title="Session",
        choices=["default", ("extended", "Extended"), Choice("programming")],
    )
    assert prompt.choice_values == ["default", "extended", "programming"]
    assert prompt.choices[1].display == "Extended"
    assert prompt.choices[0].display == "default"


def test_duplicate_choice_values_rejected():
    with pytest.raises(InteractionInvalid, match="unique"):
        Prompt(kind="single_choice", title="Session", choices=["a", "a"])


def test_inverted_integer_bounds_rejected():
    with pytest.raises(InteractionInvalid, match="above max_value"):
        Prompt(kind="integer", title="Count", min_value=10, max_value=1)


def test_default_is_validated_against_its_own_prompt():
    with pytest.raises(InteractionInvalid, match="Invalid default"):
        Prompt(kind="single_choice", title="Session",
               choices=["default"], default="nope")


def test_non_positive_timeout_rejected():
    with pytest.raises(InteractionInvalid, match="timeout must be positive"):
        Prompt(kind="text", title="Label", timeout=0)


# ── Answer coercion ──────────────────────────────────────────────────

def test_integer_accepts_digits_as_text_and_enforces_bounds():
    prompt = Prompt(kind="integer", title="DIDs", min_value=1, max_value=4096)
    assert coerce_answer(prompt, "512") == 512
    with pytest.raises(InteractionInvalid, match="at most 4096"):
        coerce_answer(prompt, 9000)
    with pytest.raises(InteractionInvalid, match="at least 1"):
        coerce_answer(prompt, 0)


def test_integer_rejects_bool_and_junk():
    prompt = Prompt(kind="integer", title="DIDs")
    with pytest.raises(InteractionInvalid):
        coerce_answer(prompt, True)
    with pytest.raises(InteractionInvalid, match="not a whole number"):
        coerce_answer(prompt, "twelve")


def test_confirm_requires_a_real_boolean():
    prompt = Prompt(kind="confirm", title="Reset the ECU?")
    assert coerce_answer(prompt, False) is False
    with pytest.raises(InteractionInvalid, match="true or false"):
        coerce_answer(prompt, "yes")


def test_required_text_rejects_whitespace_only():
    prompt = Prompt(kind="text", title="Label")
    with pytest.raises(InteractionInvalid, match="required"):
        coerce_answer(prompt, "   ")
    assert coerce_answer(Prompt(kind="text", title="Label", required=False), "") == ""


def test_text_honours_max_length():
    prompt = Prompt(kind="text", title="Label", max_length=4)
    with pytest.raises(InteractionInvalid, match="At most 4"):
        coerce_answer(prompt, "toolong")


def test_single_choice_rejects_a_value_off_the_list():
    prompt = Prompt(kind="single_choice", title="Session", choices=["default"])
    with pytest.raises(InteractionInvalid, match="not one of"):
        coerce_answer(prompt, "extended")


def test_multiple_choice_deduplicates_and_enforces_minimum():
    prompt = Prompt(kind="multiple_choice", title="ECUs",
                    choices=["gw", "bcm", "ivi"], min_selected=2)
    assert coerce_answer(prompt, ["gw", "bcm", "gw"]) == ["gw", "bcm"]
    with pytest.raises(InteractionInvalid, match="at least 2"):
        coerce_answer(prompt, ["gw"])


def test_multiple_choice_rejects_a_bare_string():
    prompt = Prompt(kind="multiple_choice", title="ECUs", choices=["gw"])
    with pytest.raises(InteractionInvalid, match="list of choice values"):
        coerce_answer(prompt, "gw")


# ── Validation schema (the client contract) ──────────────────────────

def test_schema_shape_per_kind():
    assert Prompt(kind="confirm", title="t").validation_schema() == {
        "confirm_label": "Confirm", "deny_label": "Cancel"}
    assert Prompt(kind="integer", title="t", min_value=1,
                  max_value=9).validation_schema() == {
        "required": True, "min": 1, "max": 9}
    assert Prompt(kind="single_choice", title="t",
                  choices=[("a", "A")]).validation_schema() == {
        "required": True, "choices": [{"value": "a", "label": "A"}]}


def test_schema_omits_unset_constraints():
    assert "max_length" not in Prompt(kind="text", title="t").validation_schema()
    assert "min_selected" not in Prompt(
        kind="multiple_choice", title="t", choices=["a"]).validation_schema()


# ── Sugar ────────────────────────────────────────────────────────────

def test_sugar_builds_the_right_prompt_and_returns_typed_values():
    port = RecordingPort(answer=True)
    assert port.confirm("Reset?") is True
    assert port.prompts[0].kind == "confirm"

    port = RecordingPort(answer="512")
    assert port.integer("DIDs", min_value=1) == 512
    assert port.prompts[0].min_value == 1

    port = RecordingPort(answer=["gw"])
    assert port.choose_many("ECUs", ["gw", "bcm"]) == ["gw"]
    assert port.prompts[0].min_selected == 1


def test_async_sugar_reaches_arequest():
    port = RecordingPort(answer="extended")
    result = asyncio.run(port.achoose("Session", ["default", "extended"]))
    assert result == "extended"


# ── Sync-inside-async guard ──────────────────────────────────────────

def test_guard_allows_sync_context():
    guard_sync_call("request")  # must not raise


def test_guard_refuses_a_blocking_call_from_async():
    async def main():
        guard_sync_call("request")

    with pytest.raises(InteractionInvalid, match="arequest"):
        asyncio.run(main())


# ── Execution-scoped binding ─────────────────────────────────────────

def test_no_binding_means_unavailable():
    ctx = PluginContext()
    assert ctx.has_interaction is False
    with pytest.raises(InteractionUnavailable, match="No interaction broker"):
        _ = ctx.interaction


def test_binding_is_released_after_the_block():
    ctx = PluginContext()
    port = RecordingPort()
    with bind_interaction(port):
        assert ctx.interaction is port
    assert current_interaction() is None
    with pytest.raises(InteractionUnavailable):
        _ = ctx.interaction


def test_binding_is_released_even_when_the_plugin_raises():
    with pytest.raises(RuntimeError):
        with bind_interaction(RecordingPort()):
            raise RuntimeError("plugin blew up")
    assert current_interaction() is None


def test_one_cached_context_serves_two_executions_in_turn():
    """The regression this whole design exists to prevent."""
    ctx = PluginContext()          # injected once, reused -- as in production
    first, second = RecordingPort(), RecordingPort()

    with bind_interaction(first):
        assert ctx.interaction is first
    with bind_interaction(second):
        assert ctx.interaction is second


def test_concurrent_executions_do_not_cross_prompts():
    ctx = PluginContext()
    seen: dict[str, object] = {}
    started = threading.Barrier(2)

    def run(name, port):
        with bind_interaction(port):
            started.wait(timeout=5)   # force overlap
            seen[name] = ctx.interaction

    ports = {"a": RecordingPort(), "b": RecordingPort()}
    threads = [threading.Thread(target=run, args=(n, p)) for n, p in ports.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert seen["a"] is ports["a"]
    assert seen["b"] is ports["b"]


def test_binding_does_not_leak_into_a_spawned_thread():
    """Documented caveat: contextvars do not cross threading.Thread."""
    ctx = PluginContext()
    inner: list[object] = []

    def child():
        inner.append(ctx.has_interaction)

    with bind_interaction(RecordingPort()):
        thread = threading.Thread(target=child)
        thread.start()
        thread.join(timeout=5)

    assert inner == [False]
