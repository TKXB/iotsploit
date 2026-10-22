"""Test Connection reports what it actually checked.

Only CAN has a real interface behind it. The other adapters used to return
True unconditionally, so the Configuration page showed "Connection successful"
for a UART that was never opened.
"""

from __future__ import annotations

import pytest

from iotsploit_django.tools import iot_protocol_components
from iotsploit_django.tools.iot_protocol_adapter import IoTProtocolAdapter
from iotsploit_django.tools.iot_protocol_components import CANInterfaceAdapter

pytestmark = pytest.mark.unit


def _adapter(fuzzer_available: bool) -> IoTProtocolAdapter:
    # Bypass the singleton constructor; test_connection only needs this flag.
    adapter = object.__new__(IoTProtocolAdapter)
    adapter._fuzzer_available = fuzzer_available
    return adapter


@pytest.mark.parametrize("protocol", ["uart", "spi", "ethernet", "doip"])
def test_protocols_without_a_real_interface_report_untested(protocol):
    result = _adapter(fuzzer_available=True).test_connection(
        {"protocol_type": protocol, "device_path": "/dev/ttyUSB1"}
    )

    assert result["status"] == "untested"
    assert result["connection_result"] is None
    assert result["protocol_type"] == protocol


def test_can_without_the_fuzzer_engine_reports_untested():
    result = _adapter(fuzzer_available=False).test_connection(
        {"protocol_type": "can", "device_path": "can0"}
    )

    assert result["status"] == "untested"


def test_can_interface_that_fails_to_open_reports_failure(monkeypatch):
    class Unopenable:
        def __init__(self, channel, bitrate):
            raise OSError(f"No such device: {channel}")

    monkeypatch.setattr(
        "iotsploit_fuzzer.interfaces.can_interface.SocketCANInterface", Unopenable
    )

    adapter = CANInterfaceAdapter({"device_path": "can9"}, fuzzer_available=True)

    assert adapter.test_connection() is False


def test_can_interface_that_sends_reports_success(monkeypatch):
    sent = []

    class Loopback:
        def __init__(self, channel, bitrate):
            self.channel = channel

        def send(self, data):
            sent.append((self.channel, data))

    monkeypatch.setattr(
        "iotsploit_fuzzer.interfaces.can_interface.SocketCANInterface", Loopback
    )

    result = _adapter(fuzzer_available=True).test_connection(
        {"protocol_type": "can", "device_path": "/dev/can1"}
    )

    assert result["status"] == "success"
    assert sent == [("can1", b"\x00\x01\x02\x03")]


def test_missing_protocol_type_is_an_error_with_a_message():
    result = _adapter(fuzzer_available=True).test_connection({})

    assert result["status"] == "error"
    assert "Unsupported protocol type" in result["error_message"]


def test_base_adapter_does_not_claim_a_result():
    adapter = iot_protocol_components.ProtocolInterfaceAdapter({})

    assert adapter.test_connection() is None
