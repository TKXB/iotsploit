"""The execution manager binds the interaction port around the plugin call.

Covers the wiring, not the port itself: a plugin reaching for
``ctx.interaction`` must find the port its own execution supplied, and must
find nothing once that execution is over.
"""

from __future__ import annotations

import pytest

from iotsploit_core.context import PluginContext
from iotsploit_core.core.exploit_manager import ExploitPluginManager
from iotsploit_core.core.interaction_binding import current_interaction
from iotsploit_core.ports.interaction import (
    InteractionInvalid,
    InteractionUnavailable,
    Prompt,
    PromptSugar,
    coerce_answer,
    guard_sync_call,
)

pytestmark = pytest.mark.unit


class GuardedPort(PromptSugar):
    """Applies the real sync guard, the way a production adapter does."""

    def request(self, prompt: Prompt):
        guard_sync_call("request")
        return coerce_answer(prompt, prompt.choice_values[0])

    async def arequest(self, prompt: Prompt):
        return coerce_answer(prompt, prompt.choice_values[0])

    def check_cancelled(self) -> None:
        pass

    async def acheck_cancelled(self) -> None:
        pass


class StubPort(PromptSugar):
    def __init__(self, answer):
        self.answer = answer

    def request(self, prompt: Prompt):
        return coerce_answer(prompt, self.answer)

    async def arequest(self, prompt: Prompt):
        return self.request(prompt)

    def check_cancelled(self) -> None:
        pass

    async def acheck_cancelled(self) -> None:
        pass


class PromptingPlugin:
    """A plugin that asks a question mid-run, like the real interactive ones."""

    def __init__(self):
        self.ctx = PluginContext()      # injected once, then cached
        self.seen = None
        self.raised = None

    def execute(self, target, parameters):
        try:
            self.seen = self.ctx.choose_session()
        except InteractionUnavailable as exc:
            self.raised = exc
        return {"ok": True}


def _plugin_with_helper():
    plugin = PromptingPlugin()
    plugin.ctx.choose_session = lambda: plugin.ctx.interaction.choose(
        "Session", ["default", "extended"]
    )
    return plugin


def build_manager(plugin):
    manager = ExploitPluginManager.__new__(ExploitPluginManager)
    manager._observation_sink = None
    manager._context_factory = None
    manager.plugins = {"p": plugin}
    manager.plugin_registry = {"p": {}}
    manager._load_plugin_instance = lambda name: plugin
    manager._ensure_context_injected = lambda instance: None
    return manager


def test_plugin_sees_the_port_supplied_for_its_execution():
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)

    manager.run_plugin_in_process(
        "p", target={}, parameters={}, interaction=StubPort("extended")
    )

    assert plugin.seen == "extended"
    assert plugin.raised is None


def test_binding_is_gone_once_the_run_finishes():
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)

    manager.run_plugin_in_process(
        "p", target={}, parameters={}, interaction=StubPort("default")
    )

    assert current_interaction() is None


def test_two_runs_of_one_cached_plugin_get_their_own_port():
    """A port stored on the injected context would fail exactly here."""
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)

    manager.run_plugin_in_process("p", target={}, parameters={},
                                  interaction=StubPort("default"))
    assert plugin.seen == "default"

    manager.run_plugin_in_process("p", target={}, parameters={},
                                  interaction=StubPort("extended"))
    assert plugin.seen == "extended"


def test_no_port_means_the_plugin_gets_a_clear_error():
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)

    manager.run_plugin_in_process("p", target={}, parameters={})

    assert plugin.seen is None
    assert isinstance(plugin.raised, InteractionUnavailable)
    assert "No interaction broker" in str(plugin.raised)


def test_noninteractive_plugin_is_unaffected():
    class PlainPlugin:
        def __init__(self):
            self.calls = 0

        def execute(self, target, parameters):
            self.calls += 1
            return {"ok": True}

    plugin = PlainPlugin()
    manager = build_manager(plugin)

    manager.run_plugin_in_process("p", target={}, parameters={})
    manager.run_plugin_in_process("p", target={}, parameters={},
                                  interaction=StubPort("x"))

    assert plugin.calls == 2


# ── The async path ───────────────────────────────────────────────────
#
# `run_plugin_in_process` drives `execute_async` through
# `loop.run_until_complete`. The binding has to survive that, and a blocking
# call inside it has to fail rather than deadlock the loop.

class AsyncPromptingPlugin:
    def __init__(self, blocking: bool = False):
        self.ctx = PluginContext()
        self.blocking = blocking
        self.seen = None
        self.raised = None

    async def execute_async(self, target, parameters):
        try:
            if self.blocking:
                self.seen = self.ctx.interaction.choose("Session", ["default"])
            else:
                self.seen = await self.ctx.interaction.achoose(
                    "Session", ["default", "extended"]
                )
        except Exception as exc:      # noqa: BLE001 - recorded and asserted on
            self.raised = exc
        return {"ok": True}


def test_async_plugin_reaches_the_port_through_run_until_complete():
    plugin = AsyncPromptingPlugin()
    manager = build_manager(plugin)

    manager.run_plugin_in_process(
        "p", target={}, parameters={}, interaction=StubPort("extended")
    )

    assert plugin.seen == "extended"
    assert plugin.raised is None


def test_blocking_request_inside_execute_async_fails_instead_of_deadlocking():
    """Without the guard this would hang the worker, not raise."""
    plugin = AsyncPromptingPlugin(blocking=True)
    manager = build_manager(plugin)

    manager.run_plugin_in_process(
        "p", target={}, parameters={}, interaction=GuardedPort()
    )

    assert plugin.seen is None
    assert isinstance(plugin.raised, InteractionInvalid)
    assert "achoose" in str(plugin.raised) or "arequest" in str(plugin.raised)


def test_async_plugin_without_a_port_gets_the_unavailable_error():
    plugin = AsyncPromptingPlugin()
    manager = build_manager(plugin)

    manager.run_plugin_in_process("p", target={}, parameters={})

    assert isinstance(plugin.raised, InteractionUnavailable)
