"""Bounded SCPI line sessions with explicit reconnects and exact replay evidence."""
from __future__ import annotations

import re
import socket
import time

from .base import HarnessResult, ProtocolHarness


class SCPITCPHarness(ProtocolHarness):
    DEFAULT_SEQUENCE = [{"op": "clear"}, {"op": "write_message"},
                        {"op": "clear"}, {"op": "canary"}]
    OPERATIONS = {"clear", "reconnect", "write_message", "request_read", "canary", "delay"}

    @classmethod
    def validate(cls, config):
        if not isinstance(config, dict) or config.get("mode", "scpi") != "scpi":
            raise ValueError("TCP settings must be a SCPI object")
        for key, default, maximum in (("timeout", 1000, 30000),
                                      ("case_deadline_ms", 5000, 60000),
                                      ("max_response_bytes", 8192, 65536)):
            value = config.get(key, default)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Invalid {key}")
        steps = config.get("sequence", cls.DEFAULT_SEQUENCE)
        if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
            raise ValueError("TCP sequence must contain 1 to 32 operations")
        for step in steps:
            if not isinstance(step, dict) or step.get("op") not in cls.OPERATIONS:
                raise ValueError("Unknown TCP sequence operation")
            if step["op"] == "write_message":
                value = step.get("data", "$payload")
                if not isinstance(value, str):
                    raise ValueError("Write data must be $payload or hex")
                if value != "$payload":
                    bytes.fromhex(value)
            if "response_regex" in step:
                if step["op"] != "request_read" or not isinstance(step["response_regex"], str):
                    raise ValueError("response_regex requires a read operation")
                re.compile(step["response_regex"])
            if step["op"] == "delay":
                value = step.get("ms", 0)
                if type(value) is not int or not 0 <= value <= 1000:
                    raise ValueError("Delay must be between 0 and 1000 ms")

    def __init__(self, endpoint, config, *, connector=socket.create_connection):
        if (not isinstance(endpoint, dict) or not isinstance(endpoint.get("host"), str)
                or not endpoint["host"].strip() or type(endpoint.get("port", 5025)) is not int
                or not 1 <= endpoint.get("port", 5025) <= 65535):
            raise ValueError("TCP endpoint requires host and port 1 to 65535")
        self.identity = {"transport": "tcp", "host": endpoint["host"], "port": endpoint.get("port", 5025)}
        self.address = (self.identity["host"], self.identity["port"])
        self.connector = connector
        self.base_config = dict(config)
        self.use_case(config)
        self.sock = None
        self.buffer = bytearray()
        self.baseline = None
        self.cancelled = lambda: False

    def use_case(self, settings):
        config = {**self.base_config, **settings}
        self.validate(config)
        self.config = config
        self.sequence = config.get("sequence", self.DEFAULT_SEQUENCE)

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.buffer.clear()

    def _remaining(self):
        if self.cancelled():
            raise InterruptedError("TCP campaign cancelled")
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("TCP case deadline exceeded")
        return min(left, self.config.get("timeout", 1000) / 1000)

    def _connect(self):
        if self.sock is None:
            self.sock = self.connector(self.address, timeout=self._remaining())
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.transcript.append({"op": "connect", **self.identity})
        self.sock.settimeout(self._remaining())

    def _write(self, data):
        self._connect()
        self.transcript.append({"op": "write", "data_hex": data.hex()})
        self.sock.sendall(data)

    def _read(self):
        maximum = self.config.get("max_response_bytes", 8192)
        while True:
            end = self.buffer.find(b"\n")
            if end >= 0:
                if end + 1 > maximum:
                    raise ValueError("TCP response exceeds byte limit")
                result = bytes(self.buffer[:end + 1])
                del self.buffer[:end + 1]
                self.transcript.append({"op": "read", "data_hex": result.hex()})
                return result
            if len(self.buffer) >= maximum:
                raise ValueError("TCP response reached byte limit without newline")
            self._connect()
            chunk = self.sock.recv(maximum - len(self.buffer))
            if not chunk:
                raise ConnectionError("TCP peer disconnected before response completed")
            self.buffer.extend(chunk)

    def preflight(self):
        result = self.execute(b"", sequence=[{"op": "clear"}, {"op": "canary"}])
        if not result.ok:
            raise RuntimeError(result.error)
        return self.baseline

    def execute(self, payload, *, sequence=None):
        self.deadline = time.monotonic() + self.config.get("case_deadline_ms", 5000) / 1000
        self.transcript = []
        steps = self.sequence if sequence is None else sequence
        self.validate({**self.config, "sequence": steps})
        evidence = {"protocol": "tcp", "device": self.identity, "config": {**self.config, "sequence": steps},
                    "sequence": steps, "payload_hex": payload.hex(), "transcript": self.transcript,
                    "baseline_hex": self.baseline.hex() if self.baseline else None}
        response = None
        try:
            for step in steps:
                self._remaining()
                op = step["op"]
                self.transcript.append({"op": op})
                if op in ("clear", "reconnect"):
                    # Closing resets parser/upload ownership; it is not USBTMC CLEAR.
                    self.close()
                    # Give a single-client MCU listener time to consume FIN before the next SYN.
                    time.sleep(min(0.1, self._remaining()))
                elif op == "write_message":
                    value = step.get("data", "$payload")
                    self._write(payload if value == "$payload" else bytes.fromhex(value))
                elif op == "request_read":
                    response = self._read()
                    if "response_regex" in step and not re.search(step["response_regex"], response.decode()):
                        raise ValueError(f"TCP response assertion failed: {response!r}")
                elif op == "canary":
                    self._write(b"*IDN?\n")
                    check = self._read()
                    if not check.strip() or (self.baseline is not None and check != self.baseline):
                        raise ValueError("TCP identity canary did not match baseline")
                    self.baseline = check
                    if response is None:
                        response = check
                elif op == "delay":
                    end = time.monotonic() + step.get("ms", 0) / 1000
                    while time.monotonic() < end:
                        time.sleep(min(0.01, self._remaining(), max(0, end - time.monotonic())))
            evidence["outcome"] = "completed"
            return HarnessResult(ok=True, response=response, evidence=evidence)
        except (OSError, ValueError) as exc:
            self.close()
            evidence["outcome"] = "protocol_failure"
            return HarnessResult(ok=False, response=response, error=str(exc), stop_reason=str(exc),
                                 timeout=isinstance(exc, TimeoutError), evidence=evidence,
                                 sent=any(item["op"] == "write" for item in self.transcript))
