from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SOCKET_PATH = Path("/run/iotsploit/priv.sock")
MAX_REQUEST_BYTES = 4_096
MAX_RESPONSE_BYTES = 24_576
# The daemon runs at most two commands per verb, each capped at 10 seconds, so a
# shorter patience here reports a working helper as missing.
DEFAULT_TIMEOUT_SECONDS = 25.0
INSTALL_HINT = "Install the IoTSploit privileged helper with `priv install`."

VERB_SCHEMAS = {
    "can-link-state": {"iface": "can", "state": ["up", "down"]},
    "can-up": {"iface": "can", "bitrate": "integer-or-null"},
    "doip-config": {"iface": "network"},
    "route-via": {"action": ["add", "delete"], "cidr": "ipv4-/16", "gateway": "ipv4"},
}
VERB_TABLE_HASH = hashlib.sha256(
    json.dumps(VERB_SCHEMAS, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


class PrivilegedHelperError(RuntimeError):
    pass


class PrivilegedHelperUnavailable(PrivilegedHelperError):
    pass


class PrivilegedHelperProtocolError(PrivilegedHelperError):
    pass


@dataclass(frozen=True)
class PrivilegedResult:
    ok: bool
    exit: int
    stdout: str
    stderr: str
    output_truncated: bool = False


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PrivilegedHelperProtocolError(f"duplicate response key: {key}")
        result[key] = value
    return result


def _decode_response(data: bytes) -> PrivilegedResult:
    if len(data) > MAX_RESPONSE_BYTES:
        raise PrivilegedHelperProtocolError("privileged helper response exceeds 24 KiB")
    if not data.endswith(b"\n") or data.count(b"\n") != 1:
        raise PrivilegedHelperProtocolError("privileged helper returned an incomplete or trailing response")
    try:
        payload = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrivilegedHelperProtocolError("privileged helper returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PrivilegedHelperProtocolError("privileged helper response must be an object")

    required = {"ok", "exit", "stdout", "stderr"}
    allowed = required | {"output_truncated"}
    if set(payload) - allowed or not required.issubset(payload):
        raise PrivilegedHelperProtocolError("privileged helper returned an unexpected response schema")
    if type(payload["ok"]) is not bool or type(payload["exit"]) is not int:
        raise PrivilegedHelperProtocolError("privileged helper returned invalid status fields")
    if not isinstance(payload["stdout"], str) or not isinstance(payload["stderr"], str):
        raise PrivilegedHelperProtocolError("privileged helper returned non-string output")
    truncated = payload.get("output_truncated", False)
    if type(truncated) is not bool:
        raise PrivilegedHelperProtocolError("privileged helper returned an invalid truncation flag")
    return PrivilegedResult(
        ok=payload["ok"],
        exit=payload["exit"],
        stdout=payload["stdout"],
        stderr=payload["stderr"],
        output_truncated=truncated,
    )


def call(
    verb: str,
    args: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    *,
    socket_path: str | os.PathLike[str] = DEFAULT_SOCKET_PATH,
) -> PrivilegedResult:
    if not isinstance(verb, str) or not verb:
        raise ValueError("verb must be a non-empty string")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    request = json.dumps({"verb": verb, "args": args}, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    if len(request) > MAX_REQUEST_BYTES:
        raise ValueError("privileged helper request exceeds 4 KiB")

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(float(timeout))
    try:
        client.connect(os.fspath(socket_path))
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = client.recv(4_096)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_RESPONSE_BYTES:
                raise PrivilegedHelperProtocolError("privileged helper response exceeds 24 KiB")
    except PrivilegedHelperProtocolError:
        raise
    except (OSError, TimeoutError) as exc:
        raise PrivilegedHelperUnavailable(f"Privileged helper unavailable. {INSTALL_HINT}") from exc
    finally:
        client.close()
    return _decode_response(bytes(response))
