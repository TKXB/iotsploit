"""Unit tests for pure-Python observation read-time reconciliation."""

from __future__ import annotations

from datetime import datetime

import pytest

from iotsploit_core.domain.observation import SUBJECT_SELF, ObservationRecord, ScanSummary
from iotsploit_core.domain.observation_reconcile import reconcile_observations

pytestmark = pytest.mark.unit


def _target():
    return {
        "target_id": "vw_mqb",
        "name": "VW Golf MQB",
        "buses": [
            {
                "bus_id": "b_can",
                "name": "Powertrain CAN",
                "type": "can",
                "properties": {
                    "messages": [
                        {"frame_id": 0x5A0, "name": "BusOwnedFrame", "dlc": 8, "is_extended": False}
                    ]
                },
            },
            {
                "bus_id": "b_eth",
                "name": "Diagnostic Ethernet",
                "type": "ethernet",
                "properties": {"cidr": "192.168.10.0/24"},
            },
        ],
        "components": [
            {
                "component_id": "c_gw",
                "name": "Gateway_MQB",
                "type": "gateway",
                "facets": {
                    "can": {
                        "bus_id": "b_can",
                        "messages": [
                            {"frame_id": 0x300, "name": "GW_Msg_0", "dlc": 8, "is_extended": False}
                        ],
                    },
                    "doip": {"host": "192.168.10.1", "port": 13400, "logical_address": 0x0010},
                },
            },
            {
                "component_id": "c_ivi",
                "name": "Infotainment_MIB3",
                "type": "ecu",
                "facets": {
                    "ethernet": {"interfaces": [{"ip": "192.168.10.22/24"}]},
                    "ssh": {"host": "192.168.10.22", "port": 22},
                },
            },
        ],
        "edges": [
            {"source": "c_gw", "target": "b_can", "relation": "connects"},
            {"source": "c_gw", "target": "b_eth", "relation": "connects"},
            {"source": "c_ivi", "target": "b_eth", "relation": "bus_member"},
        ],
    }


def _rec(
    *,
    scope_key: str,
    protocol: str,
    subject_kind: str,
    subject_id: str | None,
    observed_property: str = "seen",
    value=None,
    component_id: str | None = None,
    is_complete: bool = True,
) -> ObservationRecord:
    return ObservationRecord(
        scan_id="s1",
        target_id="vw_mqb",
        component_id=component_id,
        source="scanner",
        scope_key=scope_key,
        protocol=protocol,
        subject_kind=subject_kind,
        subject_id=subject_id,
        observed_property=observed_property,
        value=value,
        observed_at=datetime(2026, 11, 19, 12, 0, 0),
        is_complete=is_complete,
    )


def test_infers_can_component_and_keeps_bus_owned_frame_documented():
    records = [
        _rec(scope_key="can:b_can", protocol="can", subject_kind="message", subject_id="300", is_complete=False),
        _rec(scope_key="can:b_can", protocol="can", subject_kind="message", subject_id="5A0", is_complete=False),
        _rec(scope_key="can:b_can", protocol="can", subject_kind="message", subject_id="77F", is_complete=False),
    ]
    scans = [
        ScanSummary(scan_id="s1", source="can_live_capture", scope_key="can:b_can", is_complete=False, facts_count=3)
    ]

    reconciled, serialized_scans = reconcile_observations(_target(), records, scans)
    by_id = {item.record.subject_id: item for item in reconciled}

    assert by_id["300"].resolved_component_id == "c_gw"
    assert by_id["300"].attribution == "inferred"
    assert by_id["300"].documentation == "documented"
    assert by_id["300"].bus_id == "b_can"

    assert by_id["5A0"].resolved_component_id is None
    assert by_id["5A0"].attribution == "unclaimed"
    assert by_id["5A0"].documentation == "documented"

    assert by_id["77F"].resolved_component_id is None
    assert by_id["77F"].attribution == "unclaimed"
    assert by_id["77F"].documentation == "undocumented"

    assert serialized_scans[0]["bus_id"] == "b_can"
    assert serialized_scans[0]["is_complete"] is False


def test_infers_lan_component_and_extracts_host_key_for_unclaimed_hosts():
    records = [
        _rec(
            scope_key="lan:192.168.10.0/24:ports=22,80",
            protocol="tcp",
            subject_kind="port",
            subject_id="192.168.10.22:22",
            observed_property="state",
            value="open",
        ),
        _rec(
            scope_key="lan:192.168.10.0/24:ports=22,80",
            protocol="tcp",
            subject_kind="port",
            subject_id="192.168.10.50:80",
            observed_property="state",
            value="open",
        ),
        _rec(
            scope_key="lan:192.168.10.0/24:ports=22,80",
            protocol="ip",
            subject_kind=SUBJECT_SELF,
            subject_id=None,
            observed_property="gateway",
            value={"ip": "192.168.10.1"},
        ),
    ]

    reconciled, _ = reconcile_observations(_target(), records)
    known, unknown, self_rec = reconciled

    assert known.bus_id == "b_eth"
    assert known.host_key == "192.168.10.22"
    assert known.resolved_component_id == "c_ivi"
    assert known.attribution == "inferred"
    assert known.documentation == "documented"

    assert unknown.bus_id == "b_eth"
    assert unknown.host_key == "192.168.10.50"
    assert unknown.resolved_component_id is None
    assert unknown.attribution == "unclaimed"
    assert unknown.documentation == "unchecked"

    assert self_rec.attribution == "unclaimed"
    assert self_rec.documentation == "unchecked"
