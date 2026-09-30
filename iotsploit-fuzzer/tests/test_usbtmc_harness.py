"""Wire framing and failure evidence for the USBTMC execution owner."""
import errno
import struct
from types import SimpleNamespace

import pytest

from iotsploit_fuzzer.analysis.logger import TestLogger
from iotsploit_fuzzer.core.config import CampaignConfig, EventType
from iotsploit_fuzzer.core.orchestrator import Orchestrator
from iotsploit_fuzzer.harnesses.usbtmc_harness import USBTMCHarness
from iotsploit_fuzzer.interfaces.usbtmc_interface import resource_key

pytestmark = pytest.mark.unit


class Instrument:
    identity = {'vid': 0x1209, 'pid': 1, 'serial': '0001', 'interface': 0}
    interface, ep_out, ep_in, packet_size = 0, 1, 0x81, 64

    def __init__(self):
        self.writes = []
        self.reply = b'IoTSploit,STM32F4-Disco,0001,0.1.0\n'
        self.read_tag = 0
        self.timeout = False
        self.timeouts = 0
        self.controls = []
        self.control_replies = []

    def write(self, data, timeout):
        self.writes.append(data)
        if data[0] == 2:
            self.read_tag = data[1]
        return len(data)

    def read(self, size, timeout):
        if self.timeout or self.timeouts:
            self.timeouts = max(0, self.timeouts - 1)
            raise OSError(errno.ETIMEDOUT, 'Timeout')
        tag = self.read_tag
        return struct.pack('<BBBBIBBBB', 2, tag, tag ^ 255, 0, len(self.reply), 1, 0, 0, 0) + self.reply

    def control(self, request_type, request, value, index, size, timeout):
        self.controls.append((request, value))
        if self.control_replies:
            return self.control_replies.pop(0)
        return {5: b'\x01', 6: b'\x01\x00'}[request]  # device clear completes at once

    def clear_halt(self, endpoint):
        pass


def test_replay_preserves_wire_bytes_and_serial_identity():
    instrument = Instrument()
    harness = USBTMCHarness(instrument, {})
    harness.preflight()
    first = harness.execute(b'LED:ALL?\n')
    assert first.ok and not first.crashed
    harness.tag = first.evidence['tag_before']
    second = harness.execute(bytes.fromhex(first.evidence['payload_hex']))
    def writes(result):
        return [e['data_hex'] for e in result.evidence['transcript'] if e['op'] == 'bulk_out']
    assert writes(first) == writes(second)
    assert bytes.fromhex(writes(first)[0]) == b'\x01\x03\xfc\x00\x09\x00\x00\x00\x01\x00\x00\x00LED:ALL?\n\x00\x00\x00'
    assert resource_key(instrument.identity) != resource_key({**instrument.identity, 'serial': '1'})


def test_raw_payload_is_not_reframed_and_failure_is_not_a_crash():
    instrument = Instrument()
    harness = USBTMCHarness(instrument, {'mode': 'raw', 'sequence': [{'op': 'write_raw'}]})
    payload = b'\xff\x00\xaa\xbb'
    result = harness.execute(payload)
    assert result.ok and instrument.writes == [payload]
    instrument.timeout = True
    failed = harness.execute(payload, sequence=[{'op': 'write_raw'}, {'op': 'canary'}])
    assert not failed.ok and not failed.crashed and failed.stop_reason
    assert failed.evidence['outcome'] == 'protocol_failure'
    assert failed.evidence['transcript'][-1]['op'] == 'failure'


def test_changed_identity_stops_the_case():
    instrument = Instrument()
    harness = USBTMCHarness(instrument, {})
    harness.preflight()
    instrument.reply = b'another instrument\n'
    result = harness.execute(b'*IDN?\n')
    assert not result.ok and 'baseline' in result.stop_reason and not result.crashed


def test_timed_out_read_is_aborted_before_the_canary():
    instrument = Instrument()
    harness = USBTMCHarness(instrument, {})
    harness.preflight()
    assert instrument.controls == [(5, 0), (6, 0)]
    instrument.controls = []
    instrument.timeouts = 1
    instrument.control_replies = [b'\x01\x00', b'\x01\x00\x00\x00\x00\x00\x00\x00']
    instrument.writes = []
    result = harness.execute(b'*CLS\n')
    assert result.ok and result.timeout
    request_tag = next(data[1] for data in instrument.writes if data[0] == 2)
    assert instrument.controls == [(3, request_tag), (4, 0)]


def test_abort_with_nothing_pending_is_not_a_failure():
    instrument = Instrument()
    harness = USBTMCHarness(instrument, {})
    instrument.control_replies = [b'\x80\x02']
    result = harness.execute(b'*IDN?\n', sequence=[
        {'op': 'write_message'}, {'op': 'request_read'}, {'op': 'abort_in'}])
    assert result.ok and instrument.controls == [(3, harness.last_in_tag)]


def test_operator_stop_mid_case_is_not_a_failure(tmp_path):
    harness = USBTMCHarness(Instrument(), {})
    harness.preflight()
    events = []
    generator = SimpleNamespace(seed_corpus=lambda: [], generate=lambda seeds, total: iter([b'*IDN?\n']))
    runner = Orchestrator(generator, harness, logger_backend=TestLogger(str(tmp_path)),
                          config=CampaignConfig(iterations=1, delay=0,
                                                event_callback=lambda kind, data: events.append((kind, data))))
    stops = iter([False, False, True])
    def cancelled():
        runner._should_stop = runner._should_stop or next(stops, True)
        return runner._should_stop
    harness.cancelled = cancelled
    runner.run()
    assert EventType.TEST_CASE_COMPLETED not in [kind for kind, _ in events]
    kind, data = events[-1]
    assert kind is EventType.CAMPAIGN_STOPPED and data['reason'] == 'Stopped by operator'


@pytest.mark.parametrize('config', [
    {'mode': 'scpi', 'sequence': [{'op': 'write_raw'}]},
    {'sequence': [{'op': 'request_read', 'allow_timeout': 'false'}]},
    {'sequence': [{'op': 'request_read', 'max_bytes': 65537}]},
    {'case_deadline_ms': True},
])
def test_invalid_sequences_fail_before_io(config):
    with pytest.raises(ValueError):
        USBTMCHarness(Instrument(), config)
