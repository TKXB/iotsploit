"""The root daemon accepts only its four bounded host-state verbs."""

from __future__ import annotations

import json
import os
import runpy
import socket
import sys
import time
from pathlib import Path

import pytest

if sys.platform != "linux":
    pytest.skip("the privileged daemon is Linux-only", allow_module_level=True)

pytestmark = pytest.mark.unit

DAEMON_PATH = Path(__file__).resolve().parents[1] / "privd" / "iotsploit-privd"
DAEMON = runpy.run_path(str(DAEMON_PATH))
RequestError = DAEMON["RequestError"]


def validate(verb: str, args: dict):
    function = DAEMON["_validate_request"]
    function.__globals__["IP_EXECUTABLE"] = "/usr/sbin/ip"
    return function({"verb": verb, "args": args})


@pytest.mark.parametrize(
    ("verb", "args", "commands"),
    [
        (
            "can-up",
            {"iface": "can0", "bitrate": 500_000},
            [
                ["/usr/sbin/ip", "link", "set", "dev", "can0", "type", "can", "bitrate", "500000"],
                ["/usr/sbin/ip", "link", "set", "dev", "can0", "up"],
            ],
        ),
        (
            "can-up",
            {"iface": "vcan12", "bitrate": None},
            [["/usr/sbin/ip", "link", "set", "dev", "vcan12", "up"]],
        ),
        (
            "can-link-state",
            {"iface": "can1", "state": "down"},
            [["/usr/sbin/ip", "link", "set", "dev", "can1", "down"]],
        ),
        (
            "doip-config",
            {"iface": "eth0.10"},
            [
                ["/usr/sbin/ip", "address", "replace", "169.254.58.58/16", "dev", "eth0.10"],
                ["/usr/sbin/ip", "route", "replace", "169.254.0.0/16", "dev", "eth0.10"],
            ],
        ),
        (
            "route-via",
            {"action": "add", "cidr": "198.18.1.4/16", "gateway": "192.0.2.1"},
            [["/usr/sbin/ip", "route", "add", "198.18.0.0/16", "via", "192.0.2.1"]],
        ),
    ],
)
def test_valid_verbs_construct_fixed_argv(verb: str, args: dict, commands: list[list[str]]):
    validated_verb, validated_args, actual = validate(verb, args)

    assert validated_verb == verb
    assert set(validated_args) == set(args)
    assert actual == commands


@pytest.mark.parametrize(
    ("verb", "args"),
    [
        ("shell", {}),
        ("can-up", {"iface": "eth0", "bitrate": 500_000}),
        ("can-up", {"iface": "can0", "bitrate": None}),
        ("can-up", {"iface": "vcan0", "bitrate": 500_000}),
        ("can-up", {"iface": "can0", "bitrate": 9_999}),
        ("can-link-state", {"iface": "can0;id", "state": "up"}),
        ("can-link-state", {"iface": "can0", "state": "cycle"}),
        ("doip-config", {"iface": "ETH0"}),
        ("route-via", {"action": "add", "cidr": "10.0.0.0/8", "gateway": "192.0.2.1"}),
        ("route-via", {"action": "add", "cidr": "192.0.2.0/24", "gateway": "::1"}),
        ("route-via", {"action": "add", "cidr": "192.0.2.0/24", "gateway": "192.0.2.1", "x": 1}),
    ],
)
def test_invalid_verbs_and_arguments_are_rejected(verb: str, args: dict):
    with pytest.raises(RequestError):
        validate(verb, args)


class ChunkSocket:
    def __init__(self, chunks: list[bytes]):
        self.chunks = iter(chunks)

    def recv(self, size: int) -> bytes:
        return next(self.chunks, b"")


@pytest.mark.parametrize(
    "chunks",
    [
        [b'{"verb":"can-up","verb":"route-via","args":{}}\n', b""],
        [b'{"verb":"can-up","args":{}}\nextra', b""],
        [b'{"verb":"can-up","args":{}}', b""],
        [b"[]\n", b""],
        [b'{"verb":"can-up","args":{},"extra":1}\n', b""],
        [b"x" * 4_096, b"x\n", b""],
    ],
)
def test_malformed_partial_trailing_and_oversized_requests_are_rejected(chunks: list[bytes]):
    with pytest.raises(RequestError):
        DAEMON["_read_request"](ChunkSocket(chunks))


def executable(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake-tool"
    path.write_text("#!/usr/bin/python3\n" + body)
    path.chmod(0o755)
    return path


def test_command_output_is_capped(tmp_path: Path):
    tool = executable(tmp_path, 'import os\nos.write(1, b"o" * 9000)\nos.write(2, b"e" * 9000)\n')

    exit_code, stdout, stderr, truncated = DAEMON["_run_command"]([str(tool)])

    assert exit_code == 0
    assert len(stdout.encode()) == 8_192
    assert len(stderr.encode()) == 8_192
    assert truncated is True


def test_timeout_kills_the_started_process_group(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    tool = executable(
        tmp_path,
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen(['/bin/sleep', '10'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "time.sleep(10)\n",
    )
    run_command = DAEMON["_run_command"]
    old_timeout = run_command.__globals__["COMMAND_TIMEOUT_SECONDS"]
    # Long enough for the helper to actually register its child, short enough
    # to still time out against its 10s sleep. At 0.05s this raced CPython
    # startup plus the fork of /bin/sleep: on a loaded machine the pid file was
    # never written and the read below failed with FileNotFoundError instead of
    # testing anything. The assertions are unchanged -- only the headroom is.
    run_command.__globals__["COMMAND_TIMEOUT_SECONDS"] = 2.0
    try:
        exit_code, _, stderr, _ = run_command([str(tool), str(pid_file)])
    finally:
        run_command.__globals__["COMMAND_TIMEOUT_SECONDS"] = old_timeout

    assert exit_code == 124
    assert "timed out" in stderr
    child_pid = int(pid_file.read_text())
    for _ in range(20):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        pytest.fail("timed-out child process survived its process group")


def test_handler_emits_peer_audit_and_exact_response_schema(capsys, monkeypatch):
    handler = DAEMON["_handle_connection"]
    monkeypatch.setitem(handler.__globals__, "_execute", lambda commands: (0, "ok", "", False))
    client, daemon = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with client, daemon:
        client.sendall(b'{"verb":"can-link-state","args":{"iface":"can0","state":"up"}}\n')
        client.shutdown(socket.SHUT_WR)

        handler(daemon)
        response = json.loads(client.recv(4_096))

    audit = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert response == {"ok": True, "exit": 0, "stdout": "ok", "stderr": ""}
    assert [record["event"] for record in audit] == ["start", "finish"]
    assert audit[0]["peer_uid"] == os.getuid()
    assert audit[0]["peer_pid"] == os.getpid()
    assert audit[1]["exit"] == 0


def test_encoded_response_never_exceeds_24_kib():
    response = {"ok": True, "exit": 0, "stdout": "\x00" * 8_192, "stderr": "\x01" * 8_192}

    encoded = DAEMON["_encoded_response"](response)

    assert len(encoded) <= 24_576
    assert json.loads(encoded)["output_truncated"] is True


def test_reply_to_a_departed_caller_is_audited_not_fatal(capsys, monkeypatch):
    handler = DAEMON["_handle_connection"]
    monkeypatch.setitem(handler.__globals__, "_execute", lambda commands: (0, "ok", "", False))
    client, daemon = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with daemon:
        client.sendall(b'{"verb":"can-link-state","args":{"iface":"can0","state":"up"}}\n')
        client.shutdown(socket.SHUT_WR)
        client.close()

        handler(daemon)

    finish = [json.loads(line) for line in capsys.readouterr().err.splitlines()][-1]
    assert finish["event"] == "finish"
    assert finish["delivered"] is False


class OneShotListener:
    """Hands out a single connection, exactly as accept() would."""

    def __init__(self, connection):
        self._connection = connection

    def accept(self):
        return self._connection, None


def test_a_failing_connection_does_not_stop_the_daemon(capsys, monkeypatch):
    serve_once = DAEMON["_serve_once"]
    monkeypatch.setitem(
        serve_once.__globals__,
        "_handle_connection",
        lambda connection: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _, daemon = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    serve_once(OneShotListener(daemon))

    error = [json.loads(line) for line in capsys.readouterr().err.splitlines()][-1]
    assert error["event"] == "error"
    assert "boom" in error["error"]
