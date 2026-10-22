"""TCP framing and session recovery must preserve exact fuzz bytes and fail closed."""
import socket

import pytest

from iotsploit_fuzzer.harnesses.scpi_tcp_harness import SCPITCPHarness

pytestmark = pytest.mark.unit
QUERY = [{"op": "write_message"}, {"op": "request_read"}]


class Socket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.writes = []
        self.closed = False

    def settimeout(self, value):
        assert value > 0

    def setsockopt(self, *args):
        pass

    def sendall(self, data):
        self.writes.append(data)

    def recv(self, maximum):
        value = next(self.chunks)
        if isinstance(value, Exception):
            raise value
        assert len(value) <= maximum
        return value

    def close(self):
        self.closed = True


def harness(sockets, config=None):
    pending = iter(sockets)

    def connect(address, timeout):
        assert address == ("board", 5025)
        assert timeout > 0
        return next(pending)

    return SCPITCPHarness({"host": "board"}, config or {}, connector=connect)


def test_fragmented_lines_and_coalesced_replies_are_read_once():
    peer = Socket([b"abc", b"\ndef\n"])
    runner = harness([peer])
    payload = b"\x00*IDN?\n"

    first = runner.execute(payload, sequence=QUERY)
    second = runner.execute(b"", sequence=[{"op": "request_read"}])

    assert first.ok and first.response == b"abc\n"
    assert second.ok and second.response == b"def\n"
    assert peer.writes == [payload]
    assert first.evidence["payload_hex"] == payload.hex()
    assert first.evidence["config"]["sequence"] == QUERY


@pytest.mark.parametrize("chunks,error", [([b"abcd"], "byte limit"),
                                         ([b"abc", b""], "disconnected"),
                                         ([socket.timeout("timed out")], "timed out")])
def test_transport_failures_close_session(chunks, error):
    peer = Socket(chunks)
    runner = harness([peer], {"max_response_bytes": 4})

    result = runner.execute(b"*IDN?\n", sequence=QUERY)

    assert not result.ok and error in result.error
    assert peer.closed and result.sent


def test_reconnect_discards_pending_reply_and_checks_same_identity():
    first = Socket([b"board\nstale\n"])
    second = Socket([b"board\n"])
    runner = harness([first, Socket([]), second])
    assert runner.preflight() == b"board\n"

    result = runner.execute(b"\x00bad", sequence=runner.DEFAULT_SEQUENCE)

    assert result.ok and first.closed
    assert first.writes == [b"*IDN?\n"]
    assert second.writes == [b"*IDN?\n"]


def test_changed_identity_and_cancellation_are_failures():
    runner = harness([Socket([b"board\n"]), Socket([]), Socket([b"other\n"])])
    runner.preflight()
    assert not runner.execute(b"").ok
    runner.cancelled = lambda: True
    result = runner.execute(b"x")
    assert not result.ok and not result.sent and "cancelled" in result.error


@pytest.mark.parametrize("settings", [{"sequence": []}, {"sequence": [{"op": "abort_in"}]},
                                      {"timeout": 0}, {"mode": "raw"},
                                      {"sequence": [{"op": "write_message", "data": "zz"}]},
                                      {"sequence": [{"op": "delay", "ms": 1001}]}])
def test_invalid_case_settings_are_rejected(settings):
    runner = harness([])
    with pytest.raises(ValueError):
        runner.use_case(settings)


@pytest.mark.parametrize("endpoint", [{}, {"host": ""}, {"host": "board", "port": True},
                                      {"host": "board", "port": 65536}])
def test_invalid_endpoint_is_rejected(endpoint):
    with pytest.raises(ValueError, match="endpoint"):
        SCPITCPHarness(endpoint, {})


def test_response_assertion_fails_on_wrong_state():
    runner = harness([Socket([b"1\n"])])
    result = runner.execute(b"DUCK:STATE?\n", sequence=[
        {"op": "write_message"}, {"op": "request_read", "response_regex": "^4\\s*$"}])
    assert not result.ok and "assertion failed" in result.error


def test_case_deadline_prevents_sending_after_budget_expires(monkeypatch):
    import iotsploit_fuzzer.harnesses.scpi_tcp_harness as module
    runner = harness([], {"case_deadline_ms": 1})
    times = iter([0.0, 0.002])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    result = runner.execute(b"x")
    assert not result.ok and result.timeout and not result.sent
