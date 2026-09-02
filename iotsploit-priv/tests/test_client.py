"""The application client fails closed on absent or malformed helpers."""

from __future__ import annotations

import json
import runpy
import socket
import threading
import time
from pathlib import Path

import pytest

from iotsploit_priv import client as client_module
from iotsploit_priv.client import (
    PrivilegedHelperProtocolError,
    PrivilegedHelperUnavailable,
    call,
)

pytestmark = pytest.mark.unit


def server(path: Path, response: bytes, *, delay: float = 0) -> tuple[threading.Thread, list[bytes]]:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    received: list[bytes] = []

    def serve() -> None:
        with listener:
            connection, _ = listener.accept()
            with connection:
                request = bytearray()
                while True:
                    chunk = connection.recv(4_096)
                    if not chunk:
                        break
                    request.extend(chunk)
                received.append(bytes(request))
                time.sleep(delay)
                try:
                    connection.sendall(response)
                except BrokenPipeError:
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread, received


def test_call_sends_one_request_and_returns_typed_result(tmp_path: Path):
    path = tmp_path / "priv.sock"
    response = b'{"ok":true,"exit":0,"stdout":"done","stderr":""}\n'
    thread, received = server(path, response)

    result = call("can-link-state", {"iface": "can0", "state": "up"}, socket_path=path)
    thread.join(timeout=1)

    assert result.ok is True and result.exit == 0 and result.stdout == "done"
    assert json.loads(received[0]) == {
        "verb": "can-link-state",
        "args": {"iface": "can0", "state": "up"},
    }


def test_absent_socket_has_an_installable_unavailable_error(tmp_path: Path):
    with pytest.raises(PrivilegedHelperUnavailable, match="priv install"):
        call("can-link-state", {"iface": "can0", "state": "up"}, socket_path=tmp_path / "missing.sock")


@pytest.mark.parametrize(
    "response",
    [
        b"not-json\n",
        b'{"ok":true,"ok":false,"exit":0,"stdout":"","stderr":""}\n',
        b'{"ok":true,"exit":0,"stdout":"","stderr":""}\ntrailing',
        b'{"ok":true,"exit":0,"stdout":""}\n',
        b'[{"ok":true}]\n',
    ],
)
def test_malformed_responses_are_rejected(tmp_path: Path, response: bytes):
    path = tmp_path / "priv.sock"
    server(path, response)

    with pytest.raises(PrivilegedHelperProtocolError):
        call("can-link-state", {"iface": "can0", "state": "up"}, socket_path=path)


def test_response_timeout_is_unavailable(tmp_path: Path):
    path = tmp_path / "priv.sock"
    server(path, b'{"ok":true,"exit":0,"stdout":"","stderr":""}\n', delay=0.2)

    with pytest.raises(PrivilegedHelperUnavailable):
        call("can-link-state", {"iface": "can0", "state": "up"}, timeout=0.02, socket_path=path)


def test_oversized_request_is_rejected_before_connecting(tmp_path: Path):
    with pytest.raises(ValueError, match="4 KiB"):
        call("route-via", {"cidr": "x" * 5_000}, socket_path=tmp_path / "missing.sock")


def test_default_timeout_outlasts_the_daemon_worst_case():
    """Two commands at the daemon's per-command cap must not read as 'unavailable'."""
    daemon = runpy.run_path(str(Path(__file__).resolve().parents[1] / "privd" / "iotsploit-privd"))
    worst_case = 2 * daemon["COMMAND_TIMEOUT_SECONDS"]

    assert client_module.DEFAULT_TIMEOUT_SECONDS > worst_case
