"""The plugin manager owns the observation scan lifecycle.

The rules here are the ones that make scan history trustworthy: a scope is
opened before the plugin runs, a crash is recorded rather than lost, scan status
never comes from the plugin's own verdict, and every execution path records
exactly one lifecycle per scope.
"""

from __future__ import annotations

import asyncio

import pytest

from iotsploit_core.core.exploit_manager import ExploitPluginManager
from iotsploit_core.domain.observation import Fact, ObservationBatch, ObservationScope

pytestmark = pytest.mark.unit

TARGET = {"target_id": "zeekr_001", "name": "Zeekr"}
SCOPE = "tcam_ap_forward:fast"


class Result:
    def __init__(self, success, message="", data=None):
        self.success = success
        self.message = message
        self.data = data or {}


class RecordingSink:
    """Captures the lifecycle calls a real repository would receive."""

    def __init__(self):
        self.started = []
        self.completed = []
        self.failed = []
        self._next = 0

    def start_scans(self, *, run_id, target_id, source, scopes):
        from iotsploit_core.domain.observation import StartedScan

        started = []
        for scope in scopes:
            self._next += 1
            scan_id = f"scan{self._next}"
            self.started.append((run_id, target_id, source, scope.scope_key, scan_id))
            started.append(StartedScan(scan_id=scan_id, scope=scope))
        return started

    def complete_scan(self, scan_id, facts, *, is_complete=True):
        self.completed.append((scan_id, list(facts), is_complete))
        return len(list(facts))

    def fail_scan(self, scan_id, error_summary=None):
        self.failed.append((scan_id, error_summary))


class FakePlugin:
    """Opt-in producer whose behaviour each test dictates."""

    def __init__(self, result=None, raises=None, batches=None, scopes=None):
        self._result = result if result is not None else Result(True, "ok")
        self._raises = raises
        self._batches = batches
        self._scopes = scopes
        self.calls = 0

    def observation_scopes(self, target, parameters):
        if self._scopes is not None:
            return self._scopes
        return [ObservationScope(scope_key=SCOPE)]

    def observation_batches(self, result):
        if self._batches is not None:
            return self._batches
        return [ObservationBatch(scope_key=SCOPE, facts=[_fact("198.18.34.1")])]

    def execute(self, target, parameters):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._result


class AsyncPlugin(FakePlugin):
    async def execute_async(self, target, parameters):
        return self.execute(target, parameters)


class SilentPlugin:
    """A plugin that does not implement the producer contract."""

    def __init__(self):
        self.calls = 0

    def execute(self, target, parameters):
        self.calls += 1
        return Result(True, "ok")


def _fact(ip):
    return Fact(protocol="ip", subject_kind="host", subject_id=ip, observed_property="alive", value=True)


def build_manager(plugin, sink):
    manager = ExploitPluginManager.__new__(ExploitPluginManager)
    manager._observation_sink = sink
    manager._context_factory = None
    manager.plugins = {"p": plugin}
    manager.plugin_registry = {"p": {}}
    manager._load_plugin_instance = lambda name: plugin
    manager._ensure_context_injected = lambda instance: None
    return manager


def run_sync(manager, plugin, target=TARGET, parameters=None):
    return manager._run_with_observations(
        plugin, "p", target, parameters or {}, lambda: plugin.execute(target, parameters)
    )


def test_scope_is_opened_before_the_plugin_runs():
    """The row must exist first, or a crash looks like a scan that never ran."""
    sink, plugin = RecordingSink(), FakePlugin()
    order = []
    sink_start = sink.start_scans

    def tracking_start(**kwargs):
        order.append("start")
        return sink_start(**kwargs)

    sink.start_scans = tracking_start
    manager = build_manager(plugin, sink)

    def executor():
        order.append("execute")
        return plugin.execute(TARGET, {})

    manager._run_with_observations(plugin, "p", TARGET, {}, executor)

    assert order == ["start", "execute"]


def test_successful_run_completes_the_declared_scope():
    sink, plugin = RecordingSink(), FakePlugin()
    _, provenance = run_sync(build_manager(plugin, sink), plugin)

    assert [c[0] for c in sink.completed] == ["scan1"]
    assert sink.failed == []
    assert provenance["scan_ids"] == ["scan1"]
    assert provenance["run_id"]


def test_scan_status_is_not_taken_from_the_plugin_verdict():
    """ip_scan returns success=False when it *successfully* finds exposed hosts.
    Deriving scan status from that would record every real finding as a failure."""
    sink = RecordingSink()
    plugin = FakePlugin(result=Result(False, "TCAM AP exposed internal IPs"))
    run_sync(build_manager(plugin, sink), plugin)

    assert [c[0] for c in sink.completed] == ["scan1"]
    assert sink.failed == []


def test_empty_batch_is_recorded_as_a_complete_snapshot():
    """"Nothing exposed any more" only clears prior state if it is stored."""
    sink = RecordingSink()
    plugin = FakePlugin(batches=[ObservationBatch(scope_key=SCOPE, facts=[])])
    run_sync(build_manager(plugin, sink), plugin)

    scan_id, facts, is_complete = sink.completed[0]
    assert facts == [] and is_complete is True
    assert sink.failed == []


def test_a_crash_fails_the_scope_and_still_raises():
    sink = RecordingSink()
    plugin = FakePlugin(raises=RuntimeError("nmap died"))
    manager = build_manager(plugin, sink)

    with pytest.raises(RuntimeError):
        run_sync(manager, plugin)

    assert sink.completed == []
    assert sink.failed == [("scan1", "nmap died")]


def test_a_declared_scope_with_no_batch_is_failed_not_left_empty():
    """Otherwise an unreported scope looks like a successful empty snapshot and
    silently clears everything the previous scan found."""
    sink = RecordingSink()
    plugin = FakePlugin(batches=[])
    run_sync(build_manager(plugin, sink), plugin)

    assert sink.completed == []
    assert sink.failed == [("scan1", "plugin returned no batch for this scope")]


def test_undeclared_batches_are_ignored():
    sink = RecordingSink()
    plugin = FakePlugin(batches=[ObservationBatch(scope_key="never-declared", facts=[])])
    run_sync(build_manager(plugin, sink), plugin)

    assert sink.completed == []
    assert sink.failed == [("scan1", "plugin returned no batch for this scope")]


def test_multiple_scopes_get_one_lifecycle_each():
    sink = RecordingSink()
    scopes = [
        ObservationScope(scope_key="did:default", component_id="comp_tcam_001"),
        ObservationScope(scope_key="did:default", component_id="comp_vgm_001"),
    ]
    plugin = FakePlugin(
        scopes=scopes,
        batches=[
            ObservationBatch(scope_key="did:default", component_id="comp_tcam_001", facts=[]),
            ObservationBatch(scope_key="did:default", component_id="comp_vgm_001", facts=[]),
        ],
    )
    run_sync(build_manager(plugin, sink), plugin)

    assert len(sink.started) == 2
    assert sorted(c[0] for c in sink.completed) == ["scan1", "scan2"]
    assert sink.failed == []


def test_a_plugin_without_the_producer_contract_records_nothing():
    sink, plugin = RecordingSink(), SilentPlugin()
    result, provenance = run_sync(build_manager(plugin, sink), plugin)

    assert plugin.calls == 1
    assert sink.started == [] and provenance == {}


def test_a_target_without_an_id_records_nothing_but_still_runs():
    sink, plugin = RecordingSink(), FakePlugin()
    result, provenance = run_sync(build_manager(plugin, sink), plugin, target={})

    assert plugin.calls == 1
    assert sink.started == [] and provenance == {}


def test_a_failing_sink_never_breaks_the_plugin_result():
    """Persistence is best effort in one direction: it must not mask the run."""

    class BrokenSink(RecordingSink):
        def start_scans(self, **kwargs):
            raise RuntimeError("database is gone")

    plugin = FakePlugin()
    result, provenance = run_sync(build_manager(plugin, BrokenSink()), plugin)

    assert result.success is True
    assert provenance == {}


def test_a_failing_complete_does_not_mask_the_result():
    class BrokenSink(RecordingSink):
        def complete_scan(self, scan_id, facts, *, is_complete=True):
            raise RuntimeError("disk full")

    plugin = FakePlugin()
    result, _ = run_sync(build_manager(plugin, BrokenSink()), plugin)

    assert result.success is True


def test_in_process_and_async_paths_each_record_one_lifecycle():
    """The queued path used to call execute_async directly, so its scans were
    never recorded at all."""
    for runner in ("in_process", "async"):
        sink = RecordingSink()
        plugin = AsyncPlugin()
        manager = build_manager(plugin, sink)
        manager._normalize_target_for_plugin = lambda t: t

        if runner == "in_process":
            manager.run_plugin_in_process("p", TARGET, {})
        else:
            asyncio.run(manager.execute_plugin_async("p", TARGET, {}))

        assert len(sink.started) == 1, runner
        assert [c[0] for c in sink.completed] == ["scan1"], runner
        assert sink.failed == [], runner


def test_async_path_records_a_crash():
    sink = RecordingSink()
    plugin = AsyncPlugin(raises=RuntimeError("boom"))
    manager = build_manager(plugin, sink)
    manager._normalize_target_for_plugin = lambda t: t

    with pytest.raises(RuntimeError):
        asyncio.run(manager.execute_plugin_async("p", TARGET, {}))

    assert sink.failed == [("scan1", "boom")]
