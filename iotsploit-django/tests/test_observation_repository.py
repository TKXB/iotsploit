"""Behavior of the observation repository.

Each test pins down a rule that, if broken, makes scan results quietly wrong
rather than loudly broken -- a failed scan looking like mass disappearance, a
partial batch looking like a complete snapshot, orphaned facts outliving a scan.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from iotsploit_core.domain.observation import SUBJECT_SELF, Fact, ScanStatus
from iotsploit_django.adapters.django.observation_models import (
    ScanRunDBModel,
    enable_sqlite_foreign_keys,
    initialize_observation_schema,
)
from iotsploit_django.adapters.django.observation_repository import (
    ObservationPersistenceError,
    ObservationRepository,
)
from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db

pytestmark = pytest.mark.unit

TARGET = "zeekr_001"
SOURCE = "ip_scan"
SCOPE = "tcam_ap_forward:fast"


def host_fact(ip: str, alive: bool = True) -> Fact:
    return Fact(protocol="ip", subject_kind="host", subject_id=ip, observed_property="alive", value=alive)


@pytest.fixture
def repo(tmp_path):
    db = create_sqlalchemy_db(f"sqlite:///{tmp_path / 'observations.sqlite3'}")
    enable_sqlite_foreign_keys(db.engine)
    initialize_observation_schema(db)
    return ObservationRepository(db)


def record_scan(repo, facts, *, source=SOURCE, scope_key=SCOPE, is_complete=True, component_id=None):
    scan_id = repo.start_scan(
        target_id=TARGET, source=source, scope_key=scope_key, component_id=component_id
    )
    repo.complete_scan(scan_id, facts, is_complete=is_complete)
    return scan_id


def test_successful_empty_scan_is_recorded_as_a_complete_snapshot(repo):
    """A scan that finds nothing is evidence, not an absence of evidence."""
    scan_id = record_scan(repo, [])

    session = repo._session_factory()
    try:
        scan = session.get(ScanRunDBModel, scan_id)
        assert scan.status == ScanStatus.SUCCEEDED.value
        assert scan.is_complete is True
        assert scan.facts_count == 0
        assert scan.completed_at is not None
    finally:
        session.close()

    assert repo.current(TARGET) == []


def test_empty_snapshot_replaces_previous_snapshot(repo):
    """The host stopped answering, so it must drop out of current state."""
    record_scan(repo, [host_fact("198.18.34.1")])
    assert [r.subject_id for r in repo.current(TARGET)] == ["198.18.34.1"]

    record_scan(repo, [])

    assert repo.current(TARGET) == []


def test_failed_scan_does_not_replace_current_state(repo):
    """An outage must not be indistinguishable from a change in the target."""
    record_scan(repo, [host_fact("198.18.34.1")])

    failed = repo.start_scan(target_id=TARGET, source=SOURCE, scope_key=SCOPE)
    repo.fail_scan(failed, "wifi backend unavailable")

    current = repo.current(TARGET)
    assert [r.subject_id for r in current] == ["198.18.34.1"]


def test_incomplete_scan_does_not_define_current_state(repo):
    """Partial evidence is kept, but may not clear what a full scan established."""
    record_scan(repo, [host_fact("198.18.34.1")])
    record_scan(repo, [], is_complete=False)

    assert [r.subject_id for r in repo.current(TARGET)] == ["198.18.34.1"]


def test_scopes_do_not_overwrite_each_other(repo):
    """A fast scan finishing after a full scan must not erase the full scan's findings."""
    record_scan(repo, [host_fact("198.18.34.1")], scope_key="tcam_ap_forward:full")
    record_scan(repo, [host_fact("198.18.34.2")], scope_key="tcam_ap_forward:fast")

    assert {r.subject_id for r in repo.current(TARGET)} == {"198.18.34.1", "198.18.34.2"}


def test_batch_is_atomic(repo):
    """A duplicate identity rejects the whole batch rather than storing half of it."""
    scan_id = repo.start_scan(target_id=TARGET, source=SOURCE, scope_key=SCOPE)
    duplicated = [host_fact("198.18.34.1"), host_fact("198.18.34.1", alive=False)]

    with pytest.raises(ObservationPersistenceError):
        repo.complete_scan(scan_id, duplicated)

    assert repo.current(TARGET) == []

    session = repo._session_factory()
    try:
        scan = session.get(ScanRunDBModel, scan_id)
        assert scan.status == ScanStatus.PERSISTENCE_FAILED.value
        assert scan.is_complete is False
    finally:
        session.close()


def test_deleting_a_scan_deletes_its_observations(repo):
    """Without PRAGMA foreign_keys=ON the cascade is silently a no-op."""
    scan_id = record_scan(repo, [host_fact("198.18.34.1")])

    session = repo._session_factory()
    try:
        session.execute(text("DELETE FROM scan_runs WHERE scan_id = :sid"), {"sid": scan_id})
        session.commit()
        orphans = session.execute(
            text("SELECT COUNT(*) FROM observations WHERE scan_id = :sid"), {"sid": scan_id}
        ).scalar()
    finally:
        session.close()

    assert orphans == 0


def test_self_facts_carry_no_subject_id(repo):
    """Scalar facts about the component itself keep the open world open."""
    fact = Fact(
        protocol="adb",
        subject_kind=SUBJECT_SELF,
        observed_property="serial",
        value="MB2023DHU123456",
    )
    record_scan(repo, [fact], source="adb_enum", scope_key="devices", component_id="comp_dhu_001")

    (record,) = repo.current(TARGET)
    assert record.subject_id is None
    assert record.component_id == "comp_dhu_001"
    assert record.display_key == "adb.self.serial"


def test_subject_id_is_required_for_addressable_subjects():
    with pytest.raises(ValueError):
        Fact(protocol="uds", subject_kind="did", observed_property="response", value=None)


def test_nmap_host_entries_reduce_to_a_bare_address():
    """nmap prints "name (1.2.3.4)" only when reverse DNS answers, and the name
    differs per machine. Recording both forms would make one host look like it
    vanished and a different one appeared."""
    from iotsploit_exploits.ip_scan.ip_scan import canonical_host

    assert canonical_host("localhost (127.0.0.1)") == "127.0.0.1"
    assert canonical_host("tkxb-MS-7C95 (10.99.99.1)") == "10.99.99.1"
    assert canonical_host("198.18.34.1") == "198.18.34.1"
    assert canonical_host("  198.18.34.1  ") == "198.18.34.1"


def test_host_specs_split_on_commas_and_spaces():
    from iotsploit_exploits.ip_scan.ip_scan import parse_hosts

    assert parse_hosts("127.0.0.1,10.0.0.0/16") == ["127.0.0.1", "10.0.0.0/16"]
    assert parse_hosts("127.0.0.1 10.0.0.1") == ["127.0.0.1", "10.0.0.1"]
    assert parse_hosts("") == []
    assert parse_hosts(None) == []


@pytest.mark.parametrize(
    "spec",
    [
        "127.0.0.1; id",
        "10.0.0.0/8",
        "::1",
        123,
        " ".join(f"192.0.2.{index % 255}" for index in range(257)),
    ],
)
def test_host_specs_reject_injection_and_unbounded_scans(spec):
    from iotsploit_exploits.ip_scan.ip_scan import parse_hosts

    with pytest.raises(ValueError):
        parse_hosts(spec)


def test_self_subjects_reject_a_subject_id():
    with pytest.raises(ValueError):
        Fact(
            protocol="adb",
            subject_kind=SUBJECT_SELF,
            subject_id="something",
            observed_property="serial",
            value="x",
        )
