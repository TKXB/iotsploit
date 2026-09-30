"""USBTMC messages and explicit transport sequences with reproducible evidence."""

from __future__ import annotations

import errno
import struct
import time

from .base import HarnessResult, ProtocolHarness


class USBTMCHarness(ProtocolHarness):
    DEFAULT_SEQUENCE = [
        {"op": "write_message", "data": "$payload", "eom": True},
        {"op": "request_read", "max_bytes": 4096, "allow_timeout": True},
        {"op": "canary"},
    ]
    OPERATIONS = {"write_message", "write_raw", "request_read", "clear", "abort_out", "abort_in", "delay", "canary"}

    @classmethod
    def validate(cls, config: dict) -> None:
        if not isinstance(config, dict):
            raise ValueError("USBTMC settings must be an object")
        if config.get("mode", "scpi") not in ("scpi", "raw"):
            raise ValueError("USBTMC mode must be scpi or raw")
        for key, default, minimum, maximum in (
            ("timeout", 1000, 1, 30000), ("max_response_bytes", 4096, 1, 65536),
            ("case_deadline_ms", 5000, 1, 60000),
        ):
            value = config.get(key, default)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
        query = config.get("baseline_query", "*IDN?")
        if not isinstance(query, str) or not query or len(query.encode()) > 256:
            raise ValueError("baseline_query must be a nonempty query of at most 256 bytes")
        sequence = config.get("sequence", cls.DEFAULT_SEQUENCE)
        if not isinstance(sequence, list) or not 1 <= len(sequence) <= 32:
            raise ValueError("USBTMC sequence must contain 1 to 32 operations")
        for step in sequence:
            if not isinstance(step, dict) or step.get("op") not in cls.OPERATIONS:
                raise ValueError("Unknown USBTMC sequence operation")
            op = step["op"]
            if op == "write_raw" and config.get("mode", "scpi") != "raw":
                raise ValueError("write_raw requires raw mode")
            if op.startswith("write"):
                value = step.get("data", "$payload")
                if not isinstance(value, str):
                    raise ValueError("Write data must be $payload or hexadecimal bytes")
                if value != "$payload":
                    if len(bytes.fromhex(value)) > 65536:
                        raise ValueError("Write exceeds 65536 bytes")
                if type(step.get("eom", True)) is not bool:
                    raise ValueError("eom must be boolean")
            if op == "request_read":
                if type(step.get("allow_timeout", False)) is not bool:
                    raise ValueError("allow_timeout must be boolean")
                size = step.get("max_bytes", config.get("max_response_bytes", 4096))
                if type(size) is not int or not 1 <= size <= config.get("max_response_bytes", 4096):
                    raise ValueError("Read size exceeds max_response_bytes")
            if op == "delay":
                delay = step.get("ms", 0)
                if type(delay) is not int or not 0 <= delay <= 1000:
                    raise ValueError("Delay must be between 0 and 1000 ms")

    def __init__(self, interface, config: dict):
        self.validate(config)
        self.iface = interface
        self.config = config
        self.base_config = config
        self.sequence = config.get("sequence", self.DEFAULT_SEQUENCE)
        self.timeout = config.get("timeout", 1000)
        self.max_response = config.get("max_response_bytes", 4096)
        self.baseline_query = config.get("baseline_query", "*IDN?").encode() + b"\n"
        self.tag = 0
        self.last_out_tag = 0
        self.last_in_tag = 0
        self.cancelled = lambda: False
        self.baseline = None

    def _next_tag(self) -> int:
        self.tag = self.tag % 255 + 1
        return self.tag

    def use_case(self, settings: dict) -> None:
        """The selected case's scaffold; mutated bytes remain generator-owned."""
        config = {**self.base_config, **{key: value for key, value in settings.items()
                                   if key in ("sequence", "mode")}}
        self.validate(config)
        self.config = config
        self.sequence = config.get("sequence", self.DEFAULT_SEQUENCE)

    @staticmethod
    def frame(data: bytes, tag: int, eom: bool = True) -> bytes:
        header = struct.pack("<BBBBIBBBB", 1, tag, tag ^ 255, 0, len(data), int(eom), 0, 0, 0)
        return header + data + bytes((-len(data)) % 4)

    def _remaining(self) -> int:
        if self.cancelled():
            raise InterruptedError("USBTMC campaign cancelled")
        left = int((self.deadline - time.monotonic()) * 1000)
        if left <= 0:
            raise TimeoutError("USBTMC case deadline exceeded")
        return min(self.timeout, left)

    def _event(self, op: str, **values) -> dict:
        event = {"op": op, "at_ms": round((time.monotonic() - self.started) * 1000, 3), **values}
        self.transcript.append(event)
        return event

    def _write(self, data: bytes) -> None:
        event = self._event("bulk_out", endpoint=self.iface.ep_out, data_hex=data.hex())
        event["actual_length"] = self.iface.write(data, self._remaining())
        if event["actual_length"] != len(data):
            raise IOError("Short USBTMC bulk write")

    def _read(self, size: int) -> bytes:
        event = self._event("bulk_in", endpoint=self.iface.ep_in, requested_length=size)
        data = self.iface.read(size, self._remaining())
        event["data_hex"] = data.hex()
        return data

    def _message(self, data: bytes, eom: bool = True) -> None:
        tag = self._next_tag()
        self.last_out_tag = tag
        self._write(self.frame(data, tag, eom))

    def _response(self, maximum: int) -> bytes:
        result = bytearray()
        while len(result) < maximum:
            tag = self._next_tag()
            self.last_in_tag = tag
            wanted = maximum - len(result)
            self._write(struct.pack("<BBBBIBBBB", 2, tag, tag ^ 255, 0, wanted, 0, 0, 0, 0))
            packet = self._read(self.iface.packet_size * 16)
            if len(packet) < 12 or packet[:3] != bytes((2, tag, tag ^ 255)):
                raise ValueError("Invalid USBTMC response header or tag")
            count = struct.unpack_from("<I", packet, 4)[0]
            if count > wanted:
                raise ValueError("USBTMC response exceeds requested length")
            body = bytearray(packet[12:])
            while len(body) < count:
                chunk = self._read(self.iface.packet_size * 16)
                if not chunk:
                    raise ValueError("Empty transfer inside USBTMC response")
                body.extend(chunk)
            result.extend(body[:count])
            if packet[8] & 1:
                return bytes(result)
            if count == 0:
                raise ValueError("Empty USBTMC response without EOM")
        raise ValueError("USBTMC response reached limit without EOM")

    def _control(self, request_type: int, request: int, value: int, index: int, size: int) -> bytes:
        event = self._event("control", request_type=request_type, request=request,
                            value=value, index=index, requested_length=size)
        data = self.iface.control(request_type, request, value, index, size, self._remaining())
        event["data_hex"] = data.hex()
        return data

    def _clear(self) -> None:
        status = self._control(0xA1, 5, 0, self.iface.interface, 1)
        if status != b"\x01":
            raise ValueError("USBTMC clear initiation failed")
        while True:
            status = self._control(0xA1, 6, 0, self.iface.interface, 2)
            if len(status) != 2:
                raise ValueError("Invalid USBTMC clear status")
            if status[1] & 1:
                self._read(self.iface.packet_size * 16)
            if status[0] == 1:
                self._event("clear_halt", endpoint=self.iface.ep_out)
                self.iface.clear_halt(self.iface.ep_out)
                return
            if status[0] != 2:
                raise ValueError("USBTMC clear failed")
            time.sleep(0.01)

    def _abort(self, direction: str) -> None:
        incoming = direction == "in"
        endpoint = self.iface.ep_in if incoming else self.iface.ep_out
        tag = self.last_in_tag if incoming else self.last_out_tag
        request = 3 if incoming else 1
        status = self._control(0xA2, request, tag, endpoint, 2)
        if len(status) != 2 or status[0] not in (1, 0x80, 0x81):
            raise ValueError("USBTMC abort initiation failed")
        # STATUS_FAILED here means no transfer is in progress: nothing to abort.
        if status[0] in (0x80, 0x81):
            return
        while True:
            status = self._control(0xA2, request + 1, 0, endpoint, 8)
            if len(status) != 8:
                raise ValueError("Invalid USBTMC abort status")
            if incoming and status[1] & 1:
                self._read(self.iface.packet_size * 16)
            if status[0] == 1:
                if not incoming:
                    self._event("clear_halt", endpoint=endpoint)
                    self.iface.clear_halt(endpoint)
                return
            if status[0] != 2:
                raise ValueError("USBTMC abort failed")
            time.sleep(0.01)

    def preflight(self) -> bytes:
        result = self.execute(b"", sequence=[{"op": "canary"}])
        if not result.ok:
            raise RuntimeError(result.error)
        return self.baseline

    def execute(self, payload: bytes, *, sequence: list | None = None) -> HarnessResult:
        self.started = time.monotonic()
        self.deadline = self.started + self.config.get("case_deadline_ms", 5000) / 1000
        self.transcript = []
        steps = self.sequence if sequence is None else sequence
        evidence = {"protocol": "usbtmc", "device": self.iface.identity,
                    "config": self.config, "sequence": steps, "transcript": self.transcript,
                    "payload_hex": payload.hex(), "tag_before": self.tag,
                    "out_tag_before": self.last_out_tag, "in_tag_before": self.last_in_tag,
                    "baseline_hex": self.baseline.hex() if self.baseline else None}
        response = None
        timed_out = False
        try:
            if len(payload) > 65536:
                raise ValueError("USBTMC payload exceeds 65536 bytes")
            for index, step in enumerate(steps):
                self._remaining()
                self._event("step", index=index, operation=step["op"])
                op = step["op"]
                if op.startswith("write"):
                    value = step.get("data", "$payload")
                    data = payload if value == "$payload" else bytes.fromhex(value)
                    if op == "write_raw":
                        if len(data) >= 2 and data[0] == 1:
                            self.last_out_tag = data[1]
                        elif len(data) >= 2 and data[0] == 2:
                            self.last_in_tag = data[1]
                        self._write(data)
                    else:
                        self._message(data, step.get("eom", True))
                elif op == "request_read":
                    try:
                        response = self._response(step.get("max_bytes", self.max_response))
                    except Exception as exc:
                        if not (getattr(exc, "errno", None) == errno.ETIMEDOUT and step.get("allow_timeout", False)):
                            raise
                        self._event("expected_timeout", error=str(exc))
                        timed_out = True
                        # The device still holds the request and would answer it
                        # before any later one, under the old bTag.
                        self._abort("in")
                elif op == "canary":
                    self._message(self.baseline_query)
                    check = self._response(self.max_response)
                    if not check.strip() or (self.baseline is not None and check != self.baseline):
                        raise ValueError("USBTMC identity canary did not match baseline")
                    if self.baseline is None:
                        self.baseline = check
                    response = response if response is not None else check
                elif op == "clear":
                    self._clear()
                elif op.startswith("abort"):
                    self._abort(op.removeprefix("abort_"))
                elif op == "delay":
                    delay = step.get("ms", 0) / 1000
                    end = time.monotonic() + delay
                    while time.monotonic() < end:
                        self._remaining()
                        time.sleep(min(0.01, max(0, end - time.monotonic())))
            evidence["outcome"] = "no_reply" if timed_out else "completed"
            return HarnessResult(ok=True, response=response, timeout=timed_out, evidence=evidence)
        except Exception as exc:
            self._event("failure", error=str(exc))
            evidence["outcome"] = "cancelled" if isinstance(exc, InterruptedError) else "protocol_failure"
            return HarnessResult(ok=False, response=response,
                                 timeout=isinstance(exc, TimeoutError) or getattr(exc, "errno", None) == errno.ETIMEDOUT,
                                 error=str(exc), stop_reason=str(exc), evidence=evidence,
                                 sent=any(item["op"] in ("bulk_out", "control") for item in self.transcript))
