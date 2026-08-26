"""POST /api/preview_arxml_import/ and the create it hands off to.

The preview is the whole review boundary of the ARXML import UI: an operator
sees counts and warnings from it and only then confirms a create. Two rules
make that boundary real, and both are tested here — the preview writes nothing,
and the candidate it returns survives ``create_target`` with its buses, frames
and signals intact. A preview that lost a signal, or a create that dropped the
topology, would let a user confirm something other than what they reviewed.

The ARXML below is real: ``cantools`` parses it in strict mode and produces the
frame and signal asserted on. Nothing about the parser is mocked, so the
rejection paths (DTD, malformed XML) exercise the same code the rig runs.
"""

from __future__ import annotations

import json
import os
import tempfile

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import RequestFactory  # noqa: E402

import iotsploit_django.view_handlers.arxml_views as arxml_views  # noqa: E402
import iotsploit_django.view_handlers.target_views as target_views  # noqa: E402
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402

pytestmark = [pytest.mark.contract, pytest.mark.django]

TARGET_ID = "arxml_preview_target"


def arxml(*, category: str = "SYSTEM_DESCRIPTION") -> bytes:
    """One ECU, one CAN cluster, one frame carrying one 16-bit signal."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://autosar.org/schema/r4.0 AUTOSAR_00044.xsd">
  <AR-PACKAGES>
    <AR-PACKAGE><SHORT-NAME>System</SHORT-NAME><ELEMENTS>
      <SYSTEM><SHORT-NAME>DemoSystem</SHORT-NAME><CATEGORY>{category}</CATEGORY></SYSTEM>
    </ELEMENTS></AR-PACKAGE>
    <AR-PACKAGE><SHORT-NAME>Comm</SHORT-NAME><ELEMENTS>
      <SYSTEM-SIGNAL><SHORT-NAME>SpeedSig</SHORT-NAME></SYSTEM-SIGNAL>
      <I-SIGNAL><SHORT-NAME>SpeedISig</SHORT-NAME>
        <LENGTH>16</LENGTH>
        <SYSTEM-SIGNAL-REF DEST="SYSTEM-SIGNAL">/Comm/SpeedSig</SYSTEM-SIGNAL-REF>
      </I-SIGNAL>
      <I-SIGNAL-I-PDU><SHORT-NAME>SpeedPdu</SHORT-NAME>
        <LENGTH>8</LENGTH>
        <I-SIGNAL-TO-PDU-MAPPINGS>
          <I-SIGNAL-TO-I-PDU-MAPPING><SHORT-NAME>SpeedMapping</SHORT-NAME>
            <I-SIGNAL-REF DEST="I-SIGNAL">/Comm/SpeedISig</I-SIGNAL-REF>
            <PACKING-BYTE-ORDER>MOST-SIGNIFICANT-BYTE-LAST</PACKING-BYTE-ORDER>
            <START-POSITION>0</START-POSITION>
          </I-SIGNAL-TO-I-PDU-MAPPING>
        </I-SIGNAL-TO-PDU-MAPPINGS>
      </I-SIGNAL-I-PDU>
      <CAN-FRAME><SHORT-NAME>SpeedFrame</SHORT-NAME>
        <FRAME-LENGTH>8</FRAME-LENGTH>
        <PDU-TO-FRAME-MAPPINGS>
          <PDU-TO-FRAME-MAPPING><SHORT-NAME>SpeedPduMapping</SHORT-NAME>
            <PACKING-BYTE-ORDER>MOST-SIGNIFICANT-BYTE-LAST</PACKING-BYTE-ORDER>
            <PDU-REF DEST="I-SIGNAL-I-PDU">/Comm/SpeedPdu</PDU-REF>
            <START-POSITION>0</START-POSITION>
          </PDU-TO-FRAME-MAPPING>
        </PDU-TO-FRAME-MAPPINGS>
      </CAN-FRAME>
    </ELEMENTS></AR-PACKAGE>
    <AR-PACKAGE><SHORT-NAME>Topology</SHORT-NAME><AR-PACKAGES>
      <AR-PACKAGE><SHORT-NAME>Clusters</SHORT-NAME><ELEMENTS>
        <CAN-CLUSTER><SHORT-NAME>CAN_A</SHORT-NAME><CAN-CLUSTER-VARIANTS>
          <CAN-CLUSTER-CONDITIONAL><BAUDRATE>500000</BAUDRATE><PHYSICAL-CHANNELS>
            <CAN-PHYSICAL-CHANNEL><SHORT-NAME>CAN_A</SHORT-NAME>
              <COMM-CONNECTORS>
                <COMMUNICATION-CONNECTOR-REF-CONDITIONAL><COMMUNICATION-CONNECTOR-REF
                  DEST="CAN-COMMUNICATION-CONNECTOR">/Topology/Hardware/ECU1/CAN_A_CONN</COMMUNICATION-CONNECTOR-REF>
                </COMMUNICATION-CONNECTOR-REF-CONDITIONAL>
              </COMM-CONNECTORS>
              <FRAME-TRIGGERINGS>
                <CAN-FRAME-TRIGGERING><SHORT-NAME>SpeedFrameTrig</SHORT-NAME>
                  <FRAME-REF DEST="CAN-FRAME">/Comm/SpeedFrame</FRAME-REF>
                  <PDU-TRIGGERINGS>
                    <PDU-TRIGGERING-REF-CONDITIONAL>
                      <PDU-TRIGGERING-REF DEST="PDU-TRIGGERING">/Topology/Clusters/CAN_A/CAN_A/SpeedPduTrig</PDU-TRIGGERING-REF>
                    </PDU-TRIGGERING-REF-CONDITIONAL>
                  </PDU-TRIGGERINGS>
                  <CAN-ADDRESSING-MODE>STANDARD</CAN-ADDRESSING-MODE>
                  <IDENTIFIER>291</IDENTIFIER>
                </CAN-FRAME-TRIGGERING>
              </FRAME-TRIGGERINGS>
              <PDU-TRIGGERINGS>
                <PDU-TRIGGERING><SHORT-NAME>SpeedPduTrig</SHORT-NAME>
                  <I-PDU-REF DEST="I-SIGNAL-I-PDU">/Comm/SpeedPdu</I-PDU-REF>
                </PDU-TRIGGERING>
              </PDU-TRIGGERINGS>
            </CAN-PHYSICAL-CHANNEL>
          </PHYSICAL-CHANNELS></CAN-CLUSTER-CONDITIONAL>
        </CAN-CLUSTER-VARIANTS></CAN-CLUSTER>
      </ELEMENTS></AR-PACKAGE>
      <AR-PACKAGE><SHORT-NAME>Hardware</SHORT-NAME><ELEMENTS>
        <ECU-INSTANCE><SHORT-NAME>ECU1</SHORT-NAME><LONG-NAME><L-4 L="EN">Demo ECU</L-4></LONG-NAME>
          <CONNECTORS>
            <CAN-COMMUNICATION-CONNECTOR><SHORT-NAME>CAN_A_CONN</SHORT-NAME></CAN-COMMUNICATION-CONNECTOR>
          </CONNECTORS>
        </ECU-INSTANCE>
      </ELEMENTS></AR-PACKAGE>
    </AR-PACKAGES></AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
""".encode()


class FakeManager:
    """Stands in for the singleton, which is bound to the real database.

    Hydration is the real method, so the preview's validation and the create's
    validation are the ones production runs. Everything that would write is
    recorded instead.
    """

    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.saved = None
        self.selected = None

    def get_all_targets(self):
        return self.existing

    create_target_instance = TargetManager.create_target_instance
    _hydrate_target = staticmethod(TargetManager._hydrate_target)

    def save_target(self, instance):
        self.saved = json.loads(instance.model_dump_json())

    def set_current_target(self, instance):
        self.selected = instance


@pytest.fixture
def manager(monkeypatch):
    def install(existing=None):
        fake = FakeManager(existing)
        monkeypatch.setattr(arxml_views.TargetManager, "get_instance", staticmethod(lambda: fake))
        monkeypatch.setattr(target_views.TargetManager, "get_instance", staticmethod(lambda: fake))
        return fake

    return install


def preview(content=None, *, filename="vehicle.arxml", **fields):
    payload = {"target_id": TARGET_ID, "name": "Demo Vehicle"}
    payload.update(fields)
    payload = {key: value for key, value in payload.items() if value is not None}
    if content is not None:
        payload["file"] = SimpleUploadedFile(filename, content, content_type="application/xml")
    request = RequestFactory().post("/api/preview_arxml_import/", data=payload)
    return arxml_views.preview_arxml_import(request)


def body(response):
    return json.loads(response.content)


# ── preview ─────────────────────────────────────────────────────────


def test_preview_returns_the_whole_candidate_and_writes_nothing(manager):
    fake = manager()

    response = preview(arxml())

    assert response.status_code == 200
    data = body(response)
    assert data["status"] == "success"
    assert data["complete_vehicle"] is True
    assert data["counts"]["can_messages"] == 1
    assert data["counts"]["can_signals"] == 1
    candidate = data["candidate"]
    assert candidate["target_id"] == TARGET_ID
    assert candidate["type"] == "vehicle"
    assert candidate["status"] == "active"
    assert [bus["type"] for bus in candidate["buses"]] == ["can"]
    assert [component["type"] for component in candidate["components"]] == ["ecu"]
    assert fake.saved is None
    assert fake.selected is None


def test_preview_keeps_every_signal_field_the_frame_carries(manager):
    manager()

    candidate = body(preview(arxml()))["candidate"]

    message = candidate["buses"][0]["properties"]["messages"][0]
    assert message["frame_id"] == 0x123
    assert message["name"] == "SpeedFrame"
    assert message["dlc"] == 8
    assert message["is_extended"] is False
    signal = message["signals"][0]
    assert signal["name"] == "SpeedISig"
    assert (signal["start_bit"], signal["length"]) == (0, 16)
    assert signal["byte_order"] == "little"
    assert signal["is_float"] is False


def test_an_ecu_extract_stays_draft_and_says_so(manager):
    """The operator has to see this before confirming, not after."""
    manager()

    data = body(preview(arxml(category="ECU_SYSTEM_DESCRIPTION")))

    assert data["complete_vehicle"] is False
    assert data["candidate"]["status"] == "draft"
    assert any("ECU extract" in warning for warning in data["warnings"])


def test_provenance_records_the_basename_not_the_client_path(manager):
    """A client path is the operator's filesystem, and is never stored."""
    manager()

    data = body(preview(arxml(), filename=r"C:\oem\release\vehicle_v6.arxml"))

    metadata = data["candidate"]["properties"]["arxml_import"]
    assert metadata["source"] == "vehicle_v6.arxml"
    assert "oem" not in json.dumps(data["candidate"])


def test_an_explicit_source_label_wins_over_the_filename(manager):
    manager()

    data = body(preview(arxml(), source="OEM communication release V6.0"))

    assert data["candidate"]["properties"]["arxml_import"]["source"] == "OEM communication release V6.0"


# ── refusals ────────────────────────────────────────────────────────


def test_only_post_is_allowed():
    request = RequestFactory().get("/api/preview_arxml_import/")

    assert arxml_views.preview_arxml_import(request).status_code == 405


@pytest.mark.parametrize(
    "fields, missing",
    [
        ({"target_id": ""}, "target_id"),
        ({"name": ""}, "name"),
    ],
)
def test_identity_fields_are_required(manager, fields, missing):
    manager()

    response = preview(arxml(), **fields)

    assert response.status_code == 400
    assert missing in body(response)["error"]


def test_a_request_without_a_file_is_refused(manager):
    manager()

    response = preview(None)

    assert response.status_code == 400
    assert "file is required" in body(response)["error"]


def test_malformed_xml_is_a_correctable_400(manager):
    fake = manager()

    response = preview(b"<AUTOSAR><UNCLOSED>")

    assert response.status_code == 400
    assert "vehicle.arxml" in body(response)["error"]
    assert fake.saved is None


def test_a_dtd_is_refused_before_any_parse(manager):
    """Entity expansion is the ARXML attack surface; the parser refuses it and
    the endpoint must not turn that into a 500."""
    fake = manager()
    hostile = b'<?xml version="1.0"?><!DOCTYPE AUTOSAR [<!ENTITY x "y">]><AUTOSAR/>'

    response = preview(hostile)

    assert response.status_code == 400
    assert "DTD" in body(response)["error"]
    assert fake.saved is None


def test_an_oversize_upload_is_413_and_never_reaches_the_parser(manager, monkeypatch):
    manager()
    monkeypatch.setattr(arxml_views, "MAX_UPLOAD_BYTES", 512)

    response = preview(b"<AUTOSAR/>" + b" " * 4096)

    assert response.status_code == 413
    assert "limit" in body(response)["error"]


def test_a_server_local_path_never_reaches_the_client(manager):
    """The parser names the file it was handed, which is a temporary path."""
    manager()

    error = body(preview(b"<AUTOSAR><UNCLOSED>"))["error"]

    assert tempfile.gettempdir() not in error
    assert ".arxml" in error


@pytest.mark.parametrize(
    "content",
    [arxml(), b"<AUTOSAR><UNCLOSED>", b'<?xml version="1.0"?><!DOCTYPE A []><A/>'],
    ids=["success", "malformed", "refused"],
)
def test_the_uploaded_file_is_deleted_on_every_exit_path(manager, monkeypatch, content):
    manager()
    paths = []
    real_mkstemp = tempfile.mkstemp

    def spy(*args, **kwargs):
        handle, path = real_mkstemp(*args, **kwargs)
        paths.append(path)
        return handle, path

    monkeypatch.setattr(arxml_views.tempfile, "mkstemp", spy)

    preview(content)

    assert paths, "the view did not spool the upload to a temporary file"
    assert [path for path in paths if os.path.exists(path)] == []


# ── the create the preview hands off to ─────────────────────────────


def test_the_candidate_creates_a_target_with_its_topology_intact(manager):
    """What the operator reviewed is what gets stored -- buses, frames, signals."""
    fake = manager()
    candidate = body(preview(arxml()))["candidate"]

    request = RequestFactory().post(
        "/api/create_target/",
        data=json.dumps(candidate),
        content_type="application/json",
    )
    response = target_views.create_target(request)

    assert response.status_code == 200
    assert [bus["bus_id"] for bus in fake.saved["buses"]] == [candidate["buses"][0]["bus_id"]]
    stored = fake.saved["buses"][0]["properties"]["messages"][0]
    assert stored["name"] == "SpeedFrame"
    assert stored["signals"][0]["name"] == "SpeedISig"
    assert fake.saved["edges"][0]["relation"] == "bus_member"
    assert fake.saved["properties"]["arxml_import"]["sha256"]


def test_a_duplicate_target_id_writes_nothing(manager):
    """Release 1 has no overwrite and no merge: the operator picks a new id."""
    fake = manager(existing=[{"target_id": TARGET_ID}])
    candidate = body(preview(arxml()))["candidate"]

    request = RequestFactory().post(
        "/api/create_target/",
        data=json.dumps(candidate),
        content_type="application/json",
    )
    response = target_views.create_target(request)

    assert response.status_code == 400
    assert fake.saved is None
