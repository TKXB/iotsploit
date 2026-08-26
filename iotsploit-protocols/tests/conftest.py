"""Target fixtures for the CAN catalogue and codec.

Written here rather than vendored from a real vehicle so the suite can exercise
shapes one real file happens not to contain -- an identity claimed twice with
two different layouts, a container frame, the same number on two buses -- and
so no third-party ARXML's licence has to be reasoned about to run the tests.

The JSON shapes are the ones the importers actually write. Bus-owned frames use
what ``iotsploit_protocols.autosar.arxml`` produces, including its habit of
stringifying value-table keys on the way through JSON; component-owned frames
use what ``iotsploit_django.tools.can_facet`` dumps. A fixture that quietly
tidied either shape would test a target nobody stores.
"""

from __future__ import annotations

import pytest


def vehicle_status():
    """Ordinary little-endian frame: scaled, labelled, and counted."""
    return {
        "frame_id": 0x123,
        "name": "VehicleStatus",
        "dlc": 8,
        "is_extended": False,
        "is_fd": False,
        "cycle_time_ms": 10,
        "senders": ["VCU"],
        "signals": [
            {
                "name": "VehicleSpeed",
                "start_bit": 0,
                "length": 16,
                "byte_order": "little",
                "signed": False,
                "factor": 0.1,
                "offset": 0.0,
                "minimum": 0.0,
                "maximum": 250.0,
                "unit": "km/h",
                "multiplexer": None,
            },
            {
                "name": "IgnitionState",
                "start_bit": 16,
                "length": 2,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
                # String keys, exactly as the ARXML importer's JSON conversion
                # leaves them. Normalizing these is the catalogue's job.
                "choices": {"0": "Off", "1": "Acc", "2": "On", "3": "Crank"},
            },
            {
                "name": "AliveCounter",
                "start_bit": 18,
                "length": 4,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "minimum": 0.0,
                "maximum": 15.0,
                "unit": "",
                "multiplexer": None,
            },
        ],
    }


def vehicle_status_extended():
    """The same number as :func:`vehicle_status`, with the extended flag set.

    A different frame sharing a wire, which is why identity carries the flag.
    """
    return {
        "frame_id": 0x123,
        "name": "VehicleStatusExtended",
        "dlc": 2,
        "is_extended": True,
        "signals": [
            {
                "name": "ExtendedCounter",
                "start_bit": 0,
                "length": 16,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
            }
        ],
    }


def brake_data():
    """Motorola byte order, signed, and scaled -- the combination most likely to
    be packed wrongly by hand."""
    return {
        "frame_id": 0x2A1,
        "name": "BrakeData",
        "dlc": 8,
        "is_extended": False,
        "signals": [
            {
                "name": "BrakePressure",
                "start_bit": 7,
                "length": 16,
                "byte_order": "big",
                "signed": True,
                "factor": 0.25,
                "offset": -100.0,
                "minimum": -8292.0,
                "maximum": 8091.0,
                "unit": "bar",
                "multiplexer": None,
            },
            {
                "name": "BrakeTemp",
                "start_bit": 23,
                "length": 8,
                "byte_order": "big",
                "signed": True,
                "factor": 1.0,
                "offset": -40.0,
                "minimum": -168.0,
                "maximum": 87.0,
                "unit": "degC",
                "multiplexer": None,
            },
        ],
    }


def mux_frame():
    """One switch, two branches, and a signal common to both."""
    return {
        "frame_id": 0x300,
        "name": "MuxFrame",
        "dlc": 8,
        "is_extended": False,
        "signals": [
            {
                "name": "Mode",
                "start_bit": 0,
                "length": 8,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": "M",
            },
            {
                "name": "Common",
                "start_bit": 56,
                "length": 8,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
            },
            {
                "name": "SpeedA",
                "start_bit": 8,
                "length": 16,
                "byte_order": "little",
                "signed": False,
                "factor": 0.5,
                "offset": 0.0,
                "unit": "km/h",
                "multiplexer": "m0",
                "multiplexer_signal": "Mode",
            },
            {
                "name": "TempB",
                "start_bit": 8,
                "length": 8,
                "byte_order": "little",
                "signed": True,
                "factor": 1.0,
                "offset": -40.0,
                "unit": "degC",
                "multiplexer": "m1",
                "multiplexer_signal": "Mode",
            },
        ],
    }


def fd_frame():
    """CAN FD, and a 64-bit field no double can hold exactly."""
    return {
        "frame_id": 0x400,
        "name": "DiagnosticBlock",
        "dlc": 16,
        "is_extended": False,
        "is_fd": True,
        "signals": [
            {
                "name": "SerialNumber",
                "start_bit": 0,
                "length": 64,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
            },
            {
                "name": "BlockCounter",
                "start_bit": 64,
                "length": 32,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
            },
        ],
    }


def container_frame():
    """An AUTOSAR container. Stored so it can be refused, not encoded."""
    return {
        "frame_id": 0x500,
        "name": "ContainerPdu",
        "dlc": 64,
        "is_extended": False,
        "is_fd": True,
        "signals": [],
        "contained_messages": [
            {"name": "InnerOne", "header_id": 1, "dlc": 8, "signals": []},
            {"name": "InnerTwo", "header_id": 2, "dlc": 8, "signals": []},
        ],
    }


def conflict_frame(dlc=8):
    """Declared twice with two different payload lengths. See the component."""
    return {
        "frame_id": 0x600,
        "name": "DisputedFrame",
        "dlc": dlc,
        "is_extended": False,
        "signals": [
            {
                "name": "Value",
                "start_bit": 0,
                "length": 8,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
            }
        ],
    }


def bms_status():
    """Component-owned, and carrying a value table.

    Both halves matter: this is the shape a DBC import produces, and until the
    facet model was widened it could not hold ``choices`` at all.
    """
    return {
        "frame_id": 0x2B0,
        "name": "BmsStatus",
        "dlc": 4,
        "is_extended": False,
        "is_fd": False,
        "senders": ["BMS"],
        "signals": [
            {
                "name": "PackVoltage",
                "start_bit": 0,
                "length": 12,
                "byte_order": "little",
                "signed": False,
                "factor": 0.5,
                "offset": -100.0,
                "minimum": -100.0,
                "maximum": 1947.5,
                "unit": "V",
                "multiplexer": None,
            },
            {
                "name": "PackMode",
                "start_bit": 12,
                "length": 2,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
                "choices": {0: "Idle", 1: "Charging", 2: "Discharging", 3: "Fault"},
            },
        ],
    }


def body_status():
    """0x123 again, on another bus. Only the bus tells these two apart."""
    return {
        "frame_id": 0x123,
        "name": "BodyStatus",
        "dlc": 2,
        "is_extended": False,
        "signals": [
            {
                "name": "DoorOpen",
                "start_bit": 0,
                "length": 1,
                "byte_order": "little",
                "signed": False,
                "factor": 1.0,
                "offset": 0.0,
                "unit": "",
                "multiplexer": None,
                "choices": {"0": "Closed", "1": "Open"},
            }
        ],
    }


def bench_target():
    """A whole target, in the shape a plugin is handed one."""
    return {
        "target_id": "bench_vehicle",
        "name": "Bench Vehicle",
        "type": "vehicle",
        "status": "active",
        "buses": [
            {
                "bus_id": "bus_can_powertrain",
                "name": "Powertrain CAN",
                "type": "can",
                "properties": {
                    "messages": [
                        vehicle_status(),
                        vehicle_status_extended(),
                        brake_data(),
                        mux_frame(),
                        fd_frame(),
                        container_frame(),
                        conflict_frame(dlc=8),
                    ]
                },
            },
            {
                "bus_id": "bus_can_body",
                "name": "Body CAN",
                "type": "can",
                "properties": {"messages": [body_status()]},
            },
            {
                "bus_id": "bus_eth_backbone",
                "name": "Backbone Ethernet",
                "type": "ethernet",
                "properties": {"messages": [vehicle_status()]},
            },
        ],
        "components": [
            {
                "component_id": "c_bms",
                "name": "Battery Management",
                "type": "ecu",
                "status": "active",
                "facets": {
                    "can": {
                        "bus_id": "bus_can_powertrain",
                        "node": "BMS",
                        "messages": [bms_status(), conflict_frame(dlc=4)],
                    }
                },
                "properties": {},
            },
            {
                "component_id": "c_gateway",
                "name": "Gateway",
                "type": "ecu",
                "status": "active",
                "facets": {
                    "can": {
                        "bus_id": "bus_can_body",
                        "node": "GW",
                        "messages": [],
                    }
                },
                "properties": {},
            },
        ],
        "edges": [],
    }


@pytest.fixture
def target():
    """A fresh target per test, so a resolver that mutates its input is caught."""
    return bench_target()


@pytest.fixture
def brake_frame():
    """The Motorola frame on its own, for tests that add a second copy of it.

    Exposed as a fixture rather than imported: the root pytest config uses
    ``--import-mode=importlib``, under which a test module cannot import its
    own conftest by name.
    """
    return brake_data()
