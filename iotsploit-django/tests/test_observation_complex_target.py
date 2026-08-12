"""The observation model against a realistic multi-ECU vehicle.

The single-fact unit tests in test_observation_repository.py pin down the scan
lifecycle. This pins down what the model is *for*: several tools scanning several
components over time, and the diff between two runs staying precise. Diffing is
still done by the caller -- the repository has no diff_scans() yet -- so this also
fixes the semantics a future implementation has to preserve.
"""

from __future__ import annotations

import pytest

from iotsploit_core.domain.observation import SUBJECT_SELF, Fact
from iotsploit_django.adapters.django.observation_models import (
    enable_sqlite_foreign_keys,
    initialize_observation_schema,
)
from iotsploit_django.adapters.django.observation_repository import ObservationRepository
from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db

pytestmark = pytest.mark.integration

TARGET = "zeekr_demo_001"
TCAM = "comp_tcam_001"
DHU = "comp_dhu_001"
VGM = "comp_vgm_001"
BCM = "comp_bcm_001"


@pytest.fixture
def repo(tmp_path):
    db = create_sqlalchemy_db(f"sqlite:///{tmp_path / 'observations.sqlite3'}")
    enable_sqlite_foreign_keys(db.engine)
    initialize_observation_schema(db)
    return ObservationRepository(db)


def did(subject_id, *, nrc=None, length=0):
    return Fact(
        protocol="uds",
        subject_kind="did",
        subject_id=subject_id,
        observed_property="response",
        value={"nrc": nrc, "len": length},
    )


def host(ip):
    return Fact(protocol="ip", subject_kind="host", subject_id=ip, observed_property="alive", value=True)


def port(number):
    return Fact(protocol="tcp", subject_kind="port", subject_id=str(number), observed_property="state", value="open")


def record(repo, source, scope_key, facts, component_id=None, run_id=None):
    scan_id = repo.start_scan(
        target_id=TARGET, source=source, scope_key=scope_key, component_id=component_id, run_id=run_id
    )
    repo.complete_scan(scan_id, facts, is_complete=True)
    return scan_id


def identity(record_):
    return (
        record_.component_id,
        record_.source,
        record_.scope_key,
        record_.protocol,
        record_.subject_kind,
        record_.subject_id,
        record_.observed_property,
    )


def snapshot(repo):
    return {identity(r): r.value for r in repo.current(TARGET)}


def diff(before, after):
    appeared = after.keys() - before.keys()
    disappeared = before.keys() - after.keys()
    changed = {k for k in before.keys() & after.keys() if before[k] != after[k]}
    return appeared, disappeared, changed


def scan_round(repo, run_id, *, hosts, tcam_ports, tcam_dids, tcam_rooted):
    """One full pass of five tools over four components."""
    record(repo, "ip_scan", "tcam_ap_forward:fast", [host(ip) for ip in hosts], run_id=run_id)
    record(repo, "port_scan", "tcp:fast", [port(p) for p in tcam_ports], component_id=TCAM, run_id=run_id)
    record(repo, "port_scan", "tcp:fast", [port(22), port(80)], component_id=DHU, run_id=run_id)
    record(repo, "doip_did_enum", "did:default_session", tcam_dids, component_id=TCAM, run_id=run_id)
    record(
        repo, "doip_did_enum", "did:default_session",
        [did("F190", length=17), did("F1A0", length=8)], component_id=VGM, run_id=run_id,
    )
    record(
        repo, "can_listen", "can:CAN-B:60s",
        [Fact(protocol="can", subject_kind="message", subject_id="0x123",
              observed_property="presence", value={"dlc": 8, "period_ms": 100})],
        component_id=BCM, run_id=run_id,
    )
    record(
        repo, "adb_enum", "devices",
        [Fact(protocol="adb", subject_kind=SUBJECT_SELF, observed_property="root", value=tcam_rooted)],
        component_id=TCAM, run_id=run_id,
    )


BASELINE = dict(
    hosts=["198.18.32.1", "198.18.34.1", "198.18.36.2"],
    tcam_ports=[22, 5555, 13400],
    tcam_dids=[did("F190", length=17), did("F18C", length=12), did("F1C4", nrc="0x33")],
    tcam_rooted=False,
)

WEEK_TWO = dict(
    # the ADAS camera stopped answering; 5555 closed and 8080 opened;
    # F1C4 now answers instead of returning an NRC; F1DD is new and undocumented
    hosts=["198.18.32.1", "198.18.34.1"],
    tcam_ports=[22, 8080, 13400],
    tcam_dids=[did("F190", length=17), did("F18C", length=12), did("F1C4", length=32), did("F1DD", length=64)],
    tcam_rooted=True,
)


@pytest.fixture
def two_rounds(repo):
    scan_round(repo, "run_baseline", **BASELINE)
    before = snapshot(repo)
    scan_round(repo, "run_week2", **WEEK_TWO)
    return repo, before, snapshot(repo)


def test_diff_names_the_real_changes_and_nothing_else(two_rounds):
    """A noisy diff is a useless diff: unchanged facts must stay out of it."""
    _, before, after = two_rounds
    appeared, disappeared, changed = diff(before, after)

    assert appeared == {
        (TCAM, "doip_did_enum", "did:default_session", "uds", "did", "F1DD", "response"),
        (TCAM, "port_scan", "tcp:fast", "tcp", "port", "8080", "state"),
    }
    assert disappeared == {
        (TCAM, "port_scan", "tcp:fast", "tcp", "port", "5555", "state"),
        (None, "ip_scan", "tcam_ap_forward:fast", "ip", "host", "198.18.36.2", "alive"),
    }
    assert changed == {
        (TCAM, "adb_enum", "devices", "adb", SUBJECT_SELF, None, "root"),
        (TCAM, "doip_did_enum", "did:default_session", "uds", "did", "F1C4", "response"),
    }


def test_negative_response_becoming_positive_is_a_change_not_a_reappearance(two_rounds):
    """F1C4 was always there; only its answer changed. Losing that distinction
    would report a protected DID as newly discovered."""
    _, before, after = two_rounds
    key = (TCAM, "doip_did_enum", "did:default_session", "uds", "did", "F1C4", "response")

    assert before[key]["nrc"] == "0x33"
    assert after[key]["nrc"] is None
    appeared, disappeared, _ = diff(before, after)
    assert key not in appeared and key not in disappeared


def test_same_did_on_two_ecus_stays_two_facts(two_rounds):
    """F190 answers on both the TCAM and the VGM. Collapsing them would make
    'which components expose this DID?' unanswerable."""
    repo, _, _ = two_rounds
    answering = {
        r.component_id
        for r in repo.current(TARGET)
        if r.protocol == "uds" and r.subject_id == "F190" and r.value["nrc"] is None
    }
    assert answering == {TCAM, VGM}


def test_unrelated_scopes_are_untouched_by_a_rescan(two_rounds):
    """Rescanning the TCAM must not disturb the DHU, VGM or BCM snapshots."""
    repo, before, after = two_rounds
    for component in (DHU, VGM, BCM):
        assert {k: v for k, v in before.items() if k[0] == component} == {
            k: v for k, v in after.items() if k[0] == component
        }


def test_a_failed_rescan_does_not_look_like_mass_disappearance(two_rounds):
    """The worst possible failure mode: an outage reported as a fixed vehicle."""
    repo, _, after = two_rounds

    failed = repo.start_scan(
        target_id=TARGET, source="doip_did_enum", scope_key="did:default_session", component_id=TCAM
    )
    repo.fail_scan(failed, "DoIP routing activation refused")

    assert snapshot(repo) == after


def test_current_can_be_narrowed_to_one_component_and_tool(two_rounds):
    repo, _, _ = two_rounds
    records = repo.current(TARGET, component_id=TCAM, source="doip_did_enum")

    assert {r.subject_id for r in records} == {"F190", "F18C", "F1C4", "F1DD"}
    assert all(r.component_id == TCAM for r in records)


def test_every_fact_keeps_its_provenance(two_rounds):
    repo, _, _ = two_rounds
    (undocumented,) = [r for r in repo.current(TARGET) if r.subject_id == "F1DD"]

    assert undocumented.source == "doip_did_enum"
    assert undocumented.scope_key == "did:default_session"
    assert undocumented.component_id == TCAM
    assert undocumented.scan_id
    assert undocumented.observed_at is not None
    assert undocumented.display_key == "uds.did.F1DD.response"
