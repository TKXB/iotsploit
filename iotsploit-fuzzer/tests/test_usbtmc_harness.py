"""Wire framing and failure evidence for the USBTMC execution owner."""
import struct

import pytest

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

    def write(self, data, timeout):
        self.writes.append(data)
        if data[0] == 2:
            self.read_tag = data[1]
        return len(data)

    def read(self, size, timeout):
        if self.timeout:
            raise OSError(110, 'Timeout')
        tag = self.read_tag
        return struct.pack('<BBBBIBBBB', 2, tag, tag ^ 255, 0, len(self.reply), 1, 0, 0, 0) + self.reply


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


@pytest.mark.parametrize('config', [
    {'mode': 'scpi', 'sequence': [{'op': 'write_raw'}]},
    {'sequence': [{'op': 'request_read', 'allow_timeout': 'false'}]},
    {'sequence': [{'op': 'request_read', 'max_bytes': 65537}]},
    {'case_deadline_ms': True},
])
def test_invalid_sequences_fail_before_io(config):
    with pytest.raises(ValueError):
        USBTMCHarness(Instrument(), config)
