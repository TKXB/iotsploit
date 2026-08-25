"""Live decoded CAN sessions for the interactive CLI.

The capture plugin already publishes changed-row snapshots over the same
WebSocket used by Flutter.  This module is the terminal adapter for that
contract: it starts a durable execution, folds snapshots into a stable table,
and cancels the execution when the operator presses Ctrl-C.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:8888"
DEFAULT_WS_BASE = "ws://127.0.0.1:9999"


class CanLiveError(RuntimeError):
    """A live session could not start or finish cleanly."""


@dataclass(frozen=True)
class CanLiveRun:
    target_id: str
    bus_id: str
    channel: str
    mode: str
    duration_s: int
    max_frames: int
    snapshot_interval_ms: int = 200
    decode: bool = True
    fd: bool = True

    def plugin_payload(self) -> dict[str, Any]:
        request = {
            "schema_version": 1,
            "bus_id": self.bus_id,
            "transport": {
                "interface": "socketcan",
                "channel": self.channel,
                "fd": self.fd,
            },
            "mode": self.mode,
            "duration_s": self.duration_s,
            "max_frames": self.max_frames,
            "snapshot_interval_ms": self.snapshot_interval_ms,
            "decode": self.decode,
        }
        return {
            "plugin_name": "CAN Live Capture",
            "target_id": self.target_id,
            "parameters": {"bus_id": self.bus_id, "request": request},
        }


@dataclass
class CanSnapshotView:
    """Fold changed-row snapshots into the whole table visible to an operator."""

    rows: dict[tuple[int, bool], dict[str, Any]] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    bus_health: dict[str, int] = field(default_factory=dict)
    unknown_overflowed: bool = False
    final: bool = False

    def merge(self, message: Mapping[str, Any]) -> bool:
        envelope = message.get("data") if isinstance(message.get("data"), Mapping) else message
        if not isinstance(envelope, Mapping) or not isinstance(envelope.get("rows"), list):
            return False
        for raw_row in envelope["rows"]:
            if not isinstance(raw_row, Mapping):
                continue
            row = dict(raw_row)
            try:
                key = (int(row["frame_id"]), bool(row.get("is_extended", False)))
            except (KeyError, TypeError, ValueError):
                continue
            self.rows[key] = row
        if isinstance(envelope.get("totals"), Mapping):
            self.totals = {str(key): int(value) for key, value in envelope["totals"].items()}
        if isinstance(envelope.get("bus_health"), Mapping):
            self.bus_health = {
                str(key): int(value) for key, value in envelope["bus_health"].items()
            }
        self.unknown_overflowed = bool(envelope.get("unknown_overflowed", False))
        self.final = bool(envelope.get("final", False))
        return True

    def lines(self, run: CanLiveRun, *, width: int, height: int) -> list[str]:
        status = "complete" if self.final else "capturing"
        totals = self.totals
        lines = [
            f"CAN {run.mode} · {status}",
            f"Target {run.target_id} · Bus {run.bus_id} · Channel {run.channel}",
            (
                f"Frames {totals.get('frames', 0)} · IDs {totals.get('identities', 0)} · "
                f"Undefined {totals.get('undefined', 0)} · "
                f"Undecodable {totals.get('undecodable', 0)} · "
                f"Errors {totals.get('error_frames', 0)}"
            ),
        ]
        if self.bus_health:
            health = " · ".join(f"{key} {value}" for key, value in sorted(self.bus_health.items()))
            lines.append(f"Bus health: {health}")
        if self.unknown_overflowed:
            lines.append("Unknown identity limit reached; additional unknown IDs are not retained.")
        lines.extend(["", "ID          Count  Period   Name / last decoded", "─" * min(width, 100)])

        available_rows = max(height - len(lines) - 2, 1)
        for row in sorted(self.rows.values(), key=lambda item: (item.get("frame_id", 0), item.get("is_extended", False)))[
            :available_rows
        ]:
            identity = str(row.get("frame_id_hex") or f"0x{int(row.get('frame_id', 0)):X}")
            if row.get("is_extended"):
                identity += "x"
            period = row.get("period_ms")
            period_text = "—" if period is None else f"{period:g}ms"
            detail = _row_detail(row)
            prefix = f"{identity:<11} {int(row.get('count', 0)):>6}  {period_text:<8} "
            lines.append((prefix + detail)[:width])
        if len(self.rows) > available_rows:
            lines.append(f"… {len(self.rows) - available_rows} more identities")
        lines.append("Ctrl-C to stop")
        return lines


def _row_detail(row: Mapping[str, Any]) -> str:
    name = str(row.get("name") or "undefined")
    if row.get("decode_error_reason"):
        return f"{name} · decode failed: {row['decode_error_reason']}"
    signals = row.get("last_signals")
    if isinstance(signals, Mapping) and signals:
        pairs = [f"{key}={value}" for key, value in list(signals.items())[:3]]
        return f"{name} · " + " · ".join(pairs)
    payload = row.get("last_data_hex")
    return f"{name} · {payload}" if payload else name


class TerminalCanRenderer:
    """Render a rolling table without erasing the surrounding shell history."""

    def __init__(self, output: TextIO | None = None, *, is_tty: bool | None = None):
        self.output = output or sys.stdout
        self.is_tty = self.output.isatty() if is_tty is None else is_tty

    def __enter__(self):
        if self.is_tty:
            self.output.write("\x1b[?1049h\x1b[?25l")
            self.output.flush()
        return self

    def __exit__(self, *exc_info):
        if self.is_tty:
            self.output.write("\x1b[?25h\x1b[?1049l")
            self.output.flush()

    def show(self, view: CanSnapshotView, run: CanLiveRun) -> None:
        size = shutil.get_terminal_size((120, 30))
        lines = view.lines(run, width=size.columns, height=size.lines)
        if self.is_tty:
            self.output.write("\x1b[H\x1b[2J" + "\n".join(lines) + "\n")
        else:
            totals = view.totals
            self.output.write(
                f"{run.mode}: {totals.get('frames', 0)} frames, "
                f"{totals.get('identities', 0)} identities"
                f"{' (final)' if view.final else ''}\n"
            )
        self.output.flush()

    def finish(self, view: CanSnapshotView, run: CanLiveRun, status: str) -> None:
        totals = view.totals
        self.output.write(
            f"CAN {run.mode} {status}: {totals.get('frames', 0)} frames across "
            f"{totals.get('identities', 0)} identities; "
            f"{totals.get('undefined', 0)} undefined, "
            f"{totals.get('undecodable', 0)} undecodable, "
            f"{totals.get('error_frames', 0)} error frames.\n"
        )
        self.output.flush()


class DjangoExecutionApi:
    def __init__(self, base_url: str = DEFAULT_API_BASE):
        self.base_url = base_url.rstrip("/")

    def start(self, run: CanLiveRun) -> str:
        response = self._request("POST", "/api/execute_plugin/", run.plugin_payload())
        execution_id = response.get("execution_id")
        if not execution_id:
            raise CanLiveError(str(response.get("message") or "backend returned no execution id"))
        return str(execution_id)

    def state(self, execution_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/plugin-executions/{execution_id}/")

    def cancel(self, execution_id: str) -> None:
        self._request(
            "POST",
            f"/api/plugin-executions/{execution_id}/cancel/",
            {"reason": "CAN live CLI stopped by operator"},
        )

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-configured local service
                return json.loads(response.read().decode())
        except HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise CanLiveError(f"backend HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CanLiveError(f"cannot reach IoTSploit backend at {self.base_url}: {error}") from error


class WebSocketSnapshotStream:
    def __init__(self, url: str):
        try:
            from websockets.sync.client import connect

            self.connection = connect(url, open_timeout=5)
        except Exception as error:  # noqa: BLE001 - dependency and transport share one operator message
            raise CanLiveError(f"cannot connect to CAN snapshot stream {url}: {error}") from error

    def receive(self, timeout: float) -> Mapping[str, Any]:
        try:
            raw = self.connection.recv(timeout=timeout)
        except TimeoutError:
            raise
        except Exception as error:  # noqa: BLE001 - normalized for the session loop
            raise EOFError(str(error)) from error
        try:
            message = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as error:
            raise CanLiveError(f"CAN snapshot was not valid JSON: {error}") from error
        if not isinstance(message, Mapping):
            raise CanLiveError("CAN snapshot was not a JSON object")
        return message

    def close(self) -> None:
        self.connection.close()


class CanLiveSession:
    """Coordinate one durable execution with its separate snapshot stream."""

    TERMINAL = {"completed", "failed", "cancelled", "expired"}

    def __init__(
        self,
        *,
        api: DjangoExecutionApi | Any | None = None,
        stream_factory: Callable[[str], Any] | None = None,
        renderer: TerminalCanRenderer | Any | None = None,
        ws_base_url: str = DEFAULT_WS_BASE,
    ):
        self.api = api or DjangoExecutionApi(os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", DEFAULT_API_BASE))
        self.stream_factory = stream_factory or WebSocketSnapshotStream
        self.renderer = renderer or TerminalCanRenderer()
        self.ws_base_url = ws_base_url.rstrip("/")

    @classmethod
    def from_environment(cls, *, output: TextIO | None = None) -> "CanLiveSession":
        return cls(
            renderer=TerminalCanRenderer(output),
            ws_base_url=os.getenv("IOTSPLOIT_DJANGO_WS_BASE_URL", DEFAULT_WS_BASE),
        )

    def run(self, run: CanLiveRun) -> dict[str, Any]:
        stream_url = f"{self.ws_base_url}/ws/device/stream/can_capture_{run.bus_id}/"
        stream = self.stream_factory(stream_url)
        execution_id: str | None = None
        view = CanSnapshotView()
        status = "running"
        try:
            execution_id = self.api.start(run)
            with self.renderer:
                while not view.final:
                    try:
                        message = stream.receive(timeout=1.0)
                    except TimeoutError:
                        state = self.api.state(execution_id)
                        status = str(state.get("status") or status)
                        if status in self.TERMINAL:
                            break
                        continue
                    except EOFError:
                        state = self.api.state(execution_id)
                        status = str(state.get("status") or status)
                        if status not in self.TERMINAL:
                            raise CanLiveError("CAN snapshot stream closed before the execution finished")
                        break
                    if view.merge(message):
                        self.renderer.show(view, run)
            state = self.api.state(execution_id)
            status = str(state.get("status") or status)
            _merge_result_if_snapshot_was_missed(view, state)
        except KeyboardInterrupt:
            status = "cancelled"
            if execution_id is not None:
                self.api.cancel(execution_id)
                _receive_final_snapshot(stream, view, self.renderer, run)
        finally:
            stream.close()

        self.renderer.finish(view, run, status)
        if status == "failed":
            error = state.get("error") if "state" in locals() else None
            raise CanLiveError(f"CAN {run.mode} failed: {error}")
        return {"execution_id": execution_id, "status": status, "view": view}


def _receive_final_snapshot(stream, view, renderer, run) -> None:
    deadline = time.monotonic() + 3.0
    while not view.final and time.monotonic() < deadline:
        try:
            message = stream.receive(timeout=min(0.5, deadline - time.monotonic()))
        except (TimeoutError, EOFError):
            continue
        if view.merge(message):
            renderer.show(view, run)


def _merge_result_if_snapshot_was_missed(view: CanSnapshotView, state: Mapping[str, Any]) -> None:
    """A dropped final snapshot must not turn a successful run into zero rows."""
    if view.final:
        return
    result = state.get("result")
    data = result.get("data") if isinstance(result, Mapping) else None
    if not isinstance(data, Mapping) or not isinstance(data.get("frames"), list):
        return
    view.merge(
        {
            "rows": data["frames"],
            "totals": data.get("totals", {}),
            "bus_health": data.get("bus_health", {}),
            "unknown_overflowed": data.get("unknown_overflowed", False),
            "final": True,
        }
    )
