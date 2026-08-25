"""The CLI consumes the same changed-row CAN snapshots as Flutter.

Everything here uses fake HTTP and WebSocket adapters.  A regression must not
open a real service or SocketCAN interface merely because this command is a
live hardware surface in production.
"""

from __future__ import annotations

import cmd2
import pytest

from iotsploit_cli.can_live import (
    CanLiveRun,
    CanLiveSession,
    CanSnapshotView,
    WebSocketSnapshotStream,
)
from iotsploit_cli.commands.can_commands import CanCommands

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def run_spec(mode="capture"):
    return CanLiveRun(
        target_id="bench",
        bus_id="body",
        channel="can0",
        mode=mode,
        duration_s=30,
        max_frames=200_000,
    )


def snapshot(*, count=1, final=False):
    return {
        "data": {
            "rows": [
                {
                    "frame_id": 0x123,
                    "frame_id_hex": "0x123",
                    "is_extended": False,
                    "name": "VehicleStatus",
                    "count": count,
                    "period_ms": 10,
                    "last_signals": {"Speed": 42.5},
                }
            ],
            "totals": {
                "frames": count,
                "identities": 1,
                "undefined": 0,
                "undecodable": 0,
                "error_frames": 0,
            },
            "bus_health": {},
            "unknown_overflowed": False,
            "final": final,
        }
    }


class FakeApi:
    def __init__(self, events):
        self.events = events
        self.cancelled = []

    def start(self, run):
        self.events.append(("start", run.mode))
        return "execution-1"

    def state(self, execution_id):
        self.events.append(("state", execution_id))
        return {"status": "completed"}

    def cancel(self, execution_id):
        self.cancelled.append(execution_id)


class FakeStream:
    def __init__(self, messages, events):
        self.messages = iter(messages)
        self.events = events
        self.closed = False

    def receive(self, timeout):  # noqa: ARG002
        item = next(self.messages)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.closed = True


class FakeRenderer:
    def __init__(self):
        self.shown = []
        self.finished = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def show(self, view, run):
        self.shown.append((view.totals["frames"], run.mode))

    def finish(self, view, run, status):
        self.finished.append((view.totals.get("frames", 0), run.mode, status))


def test_websocket_close_handshake_cannot_hold_monitor_shutdown(monkeypatch):
    calls = []

    class Connection:
        pass

    def connect(url, **kwargs):
        calls.append((url, kwargs))
        return Connection()

    monkeypatch.setattr("websockets.sync.client.connect", connect)

    WebSocketSnapshotStream("ws://rig/live")

    assert calls == [
        ("ws://rig/live", {"open_timeout": 5, "close_timeout": 1})
    ]


def test_request_is_an_explicit_target_aware_monitor():
    payload = run_spec("monitor").plugin_payload()

    assert payload["plugin_name"] == "CAN Live Capture"
    assert payload["target_id"] == "bench"
    assert payload["parameters"]["bus_id"] == "body"
    assert payload["parameters"]["request"]["mode"] == "monitor"
    assert payload["parameters"]["request"]["transport"] == {
        "interface": "socketcan",
        "channel": "can0",
        "fd": True,
    }


def test_changed_rows_fold_into_one_stable_identity():
    view = CanSnapshotView()

    view.merge(snapshot(count=1))
    view.merge(snapshot(count=7, final=True))

    assert len(view.rows) == 1
    assert view.rows[(0x123, False)]["count"] == 7
    assert view.totals["frames"] == 7
    assert view.final is True


def test_live_table_renders_the_latest_decoded_value():
    view = CanSnapshotView()
    view.merge(snapshot(count=7))

    table = "\n".join(view.lines(run_spec(), width=100, height=20))

    assert "0x123" in table
    assert "VehicleStatus" in table
    assert "Speed=42.5" in table
    assert "Frames 7" in table


def test_session_connects_before_start_and_renders_the_final_snapshot():
    events = []
    stream = FakeStream([snapshot(final=True)], events)
    renderer = FakeRenderer()

    def connect(url):
        events.append(("connect", url))
        return stream

    session = CanLiveSession(
        api=FakeApi(events),
        stream_factory=connect,
        renderer=renderer,
        ws_base_url="ws://rig:9999",
    )

    result = session.run(run_spec())

    assert events[0] == ("connect", "ws://rig:9999/ws/device/stream/can_capture_body/")
    assert events[1] == ("start", "capture")
    assert renderer.shown == [(1, "capture")]
    assert renderer.finished == [(1, "capture", "completed")]
    assert result["status"] == "completed"
    assert stream.closed is True


def test_ctrl_c_cancels_the_durable_execution_and_keeps_the_final_snapshot():
    events = []
    api = FakeApi(events)
    stream = FakeStream([KeyboardInterrupt(), snapshot(count=4, final=True)], events)
    renderer = FakeRenderer()
    session = CanLiveSession(
        api=api,
        stream_factory=lambda url: stream,  # noqa: ARG005
        renderer=renderer,
    )

    result = session.run(run_spec("monitor"))

    assert api.cancelled == ["execution-1"]
    assert renderer.finished == [(4, "monitor", "cancelled")]
    assert result["status"] == "cancelled"


def test_completed_result_recovers_a_dropped_final_snapshot():
    class ResultApi(FakeApi):
        def state(self, execution_id):  # noqa: ARG002
            data = snapshot(count=9, final=True)["data"]
            return {"status": "completed", "result": {"data": {**data, "frames": data["rows"]}}}

    events = []
    stream = FakeStream([TimeoutError()], events)
    renderer = FakeRenderer()
    session = CanLiveSession(
        api=ResultApi(events),
        stream_factory=lambda url: stream,  # noqa: ARG005
        renderer=renderer,
    )

    result = session.run(run_spec())

    assert result["view"].totals["frames"] == 9
    assert result["view"].rows[(0x123, False)]["count"] == 9
    assert renderer.finished == [(9, "capture", "completed")]


class CommandSession:
    def __init__(self):
        self.runs = []

    def run(self, run):
        self.runs.append(run)
        return {"status": "completed"}


class CanShell(cmd2.Cmd, CanCommands):
    def __init__(self, session):
        super().__init__()
        self.can_live_session_factory = lambda: session


def test_canonical_monitor_command_builds_the_documented_safety_ceilings():
    session = CommandSession()
    shell = CanShell(session)

    shell.onecmd_plus_hooks("can monitor --target bench --bus body --channel can0")

    assert len(session.runs) == 1
    run = session.runs[0]
    assert run.mode == "monitor"
    assert run.duration_s == 3600
    assert run.max_frames == 20_000_000
    assert run.fd is True


def test_canonical_capture_command_honours_operator_budgets_and_classic_mode():
    session = CommandSession()
    shell = CanShell(session)

    shell.onecmd_plus_hooks(
        "can capture --target bench --bus body --channel can0 "
        "--seconds 7 --max-frames 500 --snapshot-ms 250 --classic --no-decode"
    )

    run = session.runs[0]
    assert run.mode == "capture"
    assert run.duration_s == 7
    assert run.max_frames == 500
    assert run.snapshot_interval_ms == 250
    assert run.fd is False
    assert run.decode is False
