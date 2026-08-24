from __future__ import annotations

from types import SimpleNamespace

import pytest

from iotsploit_core.domain.target import Vehicle
from iotsploit_protocols.autosar.arxml import ArxmlImportError, import_arxml

pytestmark = pytest.mark.unit


def _arxml(*, category: str = "ECU_SYSTEM_DESCRIPTION", logical_address: str = "") -> str:
    logical = f"<LOGICAL-ADDRESS>{logical_address}</LOGICAL-ADDRESS>" if logical_address else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://autosar.org/schema/r4.0 AUTOSAR_00044.xsd">
  <AR-PACKAGES>
    <AR-PACKAGE><SHORT-NAME>System</SHORT-NAME><ELEMENTS>
      <SYSTEM><SHORT-NAME>DemoSystem</SHORT-NAME><CATEGORY>{category}</CATEGORY></SYSTEM>
    </ELEMENTS></AR-PACKAGE>
    <AR-PACKAGE><SHORT-NAME>Topology</SHORT-NAME><AR-PACKAGES>
      <AR-PACKAGE><SHORT-NAME>Clusters</SHORT-NAME><ELEMENTS>
        <CAN-CLUSTER><SHORT-NAME>CAN_A</SHORT-NAME><CAN-CLUSTER-VARIANTS>
          <CAN-CLUSTER-CONDITIONAL><BAUDRATE>500000</BAUDRATE><PHYSICAL-CHANNELS>
            <CAN-PHYSICAL-CHANNEL><SHORT-NAME>CAN_A</SHORT-NAME><COMM-CONNECTORS>
              <COMMUNICATION-CONNECTOR-REF-CONDITIONAL><COMMUNICATION-CONNECTOR-REF
                DEST="CAN-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/CAN_A_CONN</COMMUNICATION-CONNECTOR-REF>
              </COMMUNICATION-CONNECTOR-REF-CONDITIONAL>
            </COMM-CONNECTORS></CAN-PHYSICAL-CHANNEL>
          </PHYSICAL-CHANNELS></CAN-CLUSTER-CONDITIONAL>
        </CAN-CLUSTER-VARIANTS></CAN-CLUSTER>
        <CAN-CLUSTER><SHORT-NAME>CAN_B</SHORT-NAME><CAN-CLUSTER-VARIANTS>
          <CAN-CLUSTER-CONDITIONAL><PHYSICAL-CHANNELS><CAN-PHYSICAL-CHANNEL>
            <SHORT-NAME>CAN_B</SHORT-NAME><COMM-CONNECTORS>
              <COMMUNICATION-CONNECTOR-REF-CONDITIONAL><COMMUNICATION-CONNECTOR-REF
                DEST="CAN-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/CAN_B_CONN</COMMUNICATION-CONNECTOR-REF>
              </COMMUNICATION-CONNECTOR-REF-CONDITIONAL>
            </COMM-CONNECTORS>
          </CAN-PHYSICAL-CHANNEL></PHYSICAL-CHANNELS></CAN-CLUSTER-CONDITIONAL>
        </CAN-CLUSTER-VARIANTS></CAN-CLUSTER>
        <LIN-CLUSTER><SHORT-NAME>LIN_A</SHORT-NAME><LIN-CLUSTER-VARIANTS>
          <LIN-CLUSTER-CONDITIONAL><BAUDRATE>19200</BAUDRATE><PHYSICAL-CHANNELS>
            <LIN-PHYSICAL-CHANNEL><SHORT-NAME>LIN_A</SHORT-NAME><COMM-CONNECTORS>
              <COMMUNICATION-CONNECTOR-REF-CONDITIONAL><COMMUNICATION-CONNECTOR-REF
                DEST="LIN-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/LIN_A_CONN</COMMUNICATION-CONNECTOR-REF>
              </COMMUNICATION-CONNECTOR-REF-CONDITIONAL>
            </COMM-CONNECTORS></LIN-PHYSICAL-CHANNEL>
          </PHYSICAL-CHANNELS></LIN-CLUSTER-CONDITIONAL>
        </LIN-CLUSTER-VARIANTS></LIN-CLUSTER>
        <ETHERNET-CLUSTER><SHORT-NAME>DIAG_ETH</SHORT-NAME><ETHERNET-CLUSTER-VARIANTS>
          <ETHERNET-CLUSTER-CONDITIONAL><PHYSICAL-CHANNELS><ETHERNET-PHYSICAL-CHANNEL>
            <SHORT-NAME>DiagChannel</SHORT-NAME><COMM-CONNECTORS>
              <COMMUNICATION-CONNECTOR-REF-CONDITIONAL><COMMUNICATION-CONNECTOR-REF
                DEST="ETHERNET-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/ETH_CONN</COMMUNICATION-CONNECTOR-REF>
              </COMMUNICATION-CONNECTOR-REF-CONDITIONAL>
            </COMM-CONNECTORS><NETWORK-ENDPOINTS><NETWORK-ENDPOINT>
              <SHORT-NAME>ECU1_EP</SHORT-NAME><INFRASTRUCTURE-SERVICES><DO-IP-ENTITY>
                <DO-IP-ENTITY-ROLE>EDGE-NODE</DO-IP-ENTITY-ROLE>{logical}
              </DO-IP-ENTITY></INFRASTRUCTURE-SERVICES><NETWORK-ENDPOINT-ADDRESSES>
                <IPV-4-CONFIGURATION><IPV-4-ADDRESS>192.0.2.10</IPV-4-ADDRESS></IPV-4-CONFIGURATION>
              </NETWORK-ENDPOINT-ADDRESSES>
            </NETWORK-ENDPOINT></NETWORK-ENDPOINTS><SO-AD-CONFIG><SOCKET-ADDRESSS>
              <SOCKET-ADDRESS><SHORT-NAME>DoIP_TCP</SHORT-NAME><APPLICATION-ENDPOINT>
                <NETWORK-ENDPOINT-REF DEST="NETWORK-ENDPOINT">/Topology/Clusters/DIAG_ETH/DiagChannel/ECU1_EP</NETWORK-ENDPOINT-REF>
                <TP-CONFIGURATION><TCP-TP><TCP-TP-PORT><PORT-NUMBER>13400</PORT-NUMBER>
                </TCP-TP-PORT></TCP-TP></TP-CONFIGURATION></APPLICATION-ENDPOINT>
                <CONNECTOR-REF DEST="ETHERNET-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/ETH_CONN</CONNECTOR-REF>
              </SOCKET-ADDRESS>
            </SOCKET-ADDRESSS></SO-AD-CONFIG>
          </ETHERNET-PHYSICAL-CHANNEL></PHYSICAL-CHANNELS></ETHERNET-CLUSTER-CONDITIONAL>
        </ETHERNET-CLUSTER-VARIANTS></ETHERNET-CLUSTER>
      </ELEMENTS></AR-PACKAGE>
      <AR-PACKAGE><SHORT-NAME>Hardware</SHORT-NAME><ELEMENTS>
        <ECU-INSTANCE><SHORT-NAME>ECU1</SHORT-NAME><LONG-NAME><L-4 L="EN">Demo ECU</L-4></LONG-NAME>
          <CONNECTORS>
            <CAN-COMMUNICATION-CONNECTOR><SHORT-NAME>CAN_A_CONN</SHORT-NAME></CAN-COMMUNICATION-CONNECTOR>
            <CAN-COMMUNICATION-CONNECTOR><SHORT-NAME>CAN_B_CONN</SHORT-NAME></CAN-COMMUNICATION-CONNECTOR>
            <LIN-COMMUNICATION-CONNECTOR><SHORT-NAME>LIN_A_CONN</SHORT-NAME></LIN-COMMUNICATION-CONNECTOR>
            <ETHERNET-COMMUNICATION-CONNECTOR><SHORT-NAME>ETH_CONN</SHORT-NAME>
              <NETWORK-ENDPOINT-REFS><NETWORK-ENDPOINT-REF DEST="NETWORK-ENDPOINT">/Topology/Clusters/DIAG_ETH/DiagChannel/ECU1_EP</NETWORK-ENDPOINT-REF></NETWORK-ENDPOINT-REFS>
            </ETHERNET-COMMUNICATION-CONNECTOR>
          </CONNECTORS>
        </ECU-INSTANCE>
      </ELEMENTS></AR-PACKAGE>
    </AR-PACKAGES></AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


def _signal(name: str = "WideSignal", length: int = 304) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        start=0,
        length=length,
        byte_order="little_endian",
        is_signed=False,
        minimum=0,
        maximum=10,
        unit="V",
        receivers=["ECU1"],
        is_multiplexer=False,
        multiplexer_ids=None,
        multiplexer_signal=None,
        conversion=SimpleNamespace(scale=0.5, offset=1, choices={0: "Off"}),
    )


def _message(bus: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        bus_name=bus,
        frame_id=0x123,
        name=name,
        length=64,
        is_extended_frame=False,
        is_fd=True,
        cycle_time=20,
        senders=["ECU1"],
        header_id=None,
        contained_messages=[],
        signals=[_signal()],
    )


def _database() -> SimpleNamespace:
    return SimpleNamespace(
        buses=[
            SimpleNamespace(name="CAN_A", baudrate=500000, fd_baudrate=2000000),
            SimpleNamespace(name="CAN_B", baudrate=500000, fd_baudrate=None),
        ],
        messages=[_message("CAN_A", "SharedFrame"), _message("CAN_B", "SharedFrame")],
    )


def test_import_projects_topology_and_keeps_same_frame_on_each_bus(tmp_path):
    path = tmp_path / "demo.arxml"
    path.write_text(_arxml(), encoding="utf-8")
    calls = []

    def loader(filename, **kwargs):
        calls.append((filename, kwargs))
        return _database()

    result = import_arxml(path, target_id="demo", name="Demo", load_file=loader)

    assert calls == [(str(path), {"database_format": "arxml", "strict": True})]
    assert result.target["status"] == "draft"
    assert result.target["properties"]["arxml_import"]["complete_vehicle"] is False
    assert result.counts == {
        "components": 1,
        "buses": 4,
        "edges": 4,
        "can_messages": 2,
        "can_signals": 2,
        "can_fd_messages": 2,
        "can_container_messages": 0,
    }
    can_buses = [bus for bus in result.target["buses"] if bus["type"] == "can"]
    assert [bus["properties"]["messages"][0]["frame_id"] for bus in can_buses] == [
        0x123,
        0x123,
    ]
    assert can_buses[0]["properties"]["messages"][0]["signals"][0]["length"] == 304
    assert all("_connector_refs" not in bus for bus in result.target["buses"])


def test_ethernet_endpoint_is_owned_without_fabricating_doip_facet(tmp_path):
    path = tmp_path / "demo.arxml"
    path.write_text(_arxml(), encoding="utf-8")

    result = import_arxml(path, target_id="demo", name="Demo", load_file=lambda *_a, **_k: _database())
    ecu = result.target["components"][0]

    assert ecu["properties"]["ip_address"] == "192.0.2.10"
    assert ecu["properties"]["sockets"][0]["port"] == 13400
    assert ecu["facets"] == {}
    assert any("no logical address" in warning for warning in result.warnings)


def test_doip_facet_is_created_only_when_logical_address_exists(tmp_path):
    path = tmp_path / "demo.arxml"
    path.write_text(_arxml(logical_address="0x1234"), encoding="utf-8")

    result = import_arxml(path, target_id="demo", name="Demo", load_file=lambda *_a, **_k: _database())

    assert result.target["components"][0]["facets"]["doip"] == {
        "logical_address": 0x1234,
        "host": "192.0.2.10",
        "port": 13400,
    }


def test_complete_system_is_active_and_target_model_validates_edges(tmp_path):
    path = tmp_path / "demo.arxml"
    path.write_text(_arxml(category="SYSTEM_DESCRIPTION"), encoding="utf-8")

    result = import_arxml(path, target_id="demo", name="Demo", load_file=lambda *_a, **_k: _database())
    vehicle = Vehicle.model_validate(result.target)

    assert vehicle.status == "active"
    assert result.target["properties"]["arxml_import"]["complete_vehicle"] is True
    assert len(vehicle.edges) == 4


def test_dtd_is_rejected_before_cantools_runs(tmp_path):
    path = tmp_path / "unsafe.arxml"
    path.write_text('<!DOCTYPE x [<!ENTITY e "unsafe">]><AUTOSAR/>', encoding="utf-8")
    called = False

    def loader(*_args, **_kwargs):
        nonlocal called
        called = True
        return _database()

    with pytest.raises(ArxmlImportError, match="DTD or entity"):
        import_arxml(path, target_id="demo", name="Demo", load_file=loader)
    assert called is False
