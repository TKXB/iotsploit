"""The execution manager binds the interaction port around the plugin call.

Covers the wiring, not the port itself: a plugin reaching for
``ctx.interaction`` must find the port its own execution supplied, and must
find nothing once that execution is over.
"""

from __future__ import annotations

import pytest

from iotsploit_core.context import PluginContext
from iotsploit_core.core.exploit_manager import ExploitPluginManager
from iotsploit_core.core.interaction_binding import bind_interaction, current_interaction
from iotsploit_core.ports.interaction import (
    InteractionInvalid,
    InteractionUnavailable,
    Prompt,
    PromptSugar,
    coerce_answer,
    guard_sync_call,
)
from iotsploit_core.platforms.capability import Availability

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


def test_an_outer_binding_reaches_a_run_that_supplies_no_port():
    """How the shell's port reaches nested group and sequence execution."""
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)
    shell_port = StubPort("extended")

    with bind_interaction(shell_port):
        manager.run_plugin_in_process("p", target={}, parameters={})

    assert plugin.seen == "extended"
    assert plugin.raised is None


def test_an_explicit_port_wins_over_the_outer_one():
    plugin = _plugin_with_helper()
    manager = build_manager(plugin)

    with bind_interaction(StubPort("default")):
        manager.run_plugin_in_process(
            "p", target={}, parameters={}, interaction=StubPort("extended")
        )

    assert plugin.seen == "extended"


def test_shell_bound_interactive_plugin_stays_in_process_despite_duration_hint():
    class LongInteractivePlugin:
        def __init__(self):
            self.calls = 0

        def get_info(self):
            return {"Interactive": True}

        def execute(self, target, parameters):
            self.calls += 1
            return {"ok": True}

    class RejectingTaskRunner:
        def submit(self, *args, **kwargs):
            raise AssertionError("interactive shell run escaped to the task queue")

    plugin = LongInteractivePlugin()
    manager = build_manager(plugin)
    manager._task_runner = RejectingTaskRunner()
    manager._run_with_observations = (
        lambda instance, name, target, parameters, executor: (executor(), {})
    )

    with bind_interaction(StubPort("unused")):
        result = manager.execute_plugin("p", parameters={"duration": 30})

    assert plugin.calls == 1
    assert result["message"] == "{'ok': True}"


def test_unbound_interactive_plugin_goes_to_the_task_runner():
    """The Control Panel's path: no port here, so the durable runner must get it.

    Interactive metadata is the whole trigger. A plugin with no
    ``execute_async`` and no async hint in its parameters still has to leave
    this process, because the operator answers over HTTP and running it here
    would only produce InteractionUnavailable.
    """

    class QuietInteractivePlugin:
        def __init__(self):
            self.calls = 0

        def get_info(self):
            return {"Interactive": True}

        def execute(self, target, parameters):
            self.calls += 1
            return {"ok": True}

    class RecordingTaskRunner:
        def __init__(self):
            self.submitted = []

        def submit(self, plugin_name, target=None, parameters=None, *, context=None):
            self.submitted.append((plugin_name, context))
            return {"execution_type": "interactive", "execution_id": "abc"}

    plugin = QuietInteractivePlugin()
    manager = build_manager(plugin)
    runner = RecordingTaskRunner()
    manager._task_runner = runner

    result = manager.execute_plugin("p", parameters={})

    assert plugin.calls == 0
    assert result["execution_type"] == "interactive"
    assert runner.submitted == [("p", {"interactive": True})]


def test_dispatcher_does_not_apply_its_availability_to_a_worker_run():
    class Plugin:
        def get_info(self):
            return {"Interactive": True}

        def execute(self, target, parameters):
            raise AssertionError("worker-bound plugin ran in the dispatcher")

    class UnavailableResolver:
        def resolve(self, requirements):
            return Availability(False, "unavailable on dispatcher")

    class RecordingTaskRunner:
        def submit(self, plugin_name, target=None, parameters=None, *, context=None):
            return {"execution_id": "worker-run"}

    manager = build_manager(Plugin())
    manager._capability_resolver = UnavailableResolver()
    manager._task_runner = RecordingTaskRunner()

    assert manager.execute_plugin("p") == {"execution_id": "worker-run"}
