"""Repository for target observations (adapter layer).

Deliberately small: start a scan, complete it, fail it, read current state. Diff,
history and listing are not here yet -- see docs/target_data_model_plan.md,
"Phase 1 minimal". The first diff is computed by hand against ``current()`` so the
model is validated against real hardware before more query surface is built.

Facts are never updated in place. A new scan appends a new row; ``current()``
derives the present view by selecting the latest successful complete scan per
comparable scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from iotsploit_core.domain.observation import (
    Fact,
    ObservationRecord,
    ObservationScope,
    ScanStatus,
    ScanSummary,
    StartedScan,
)
from iotsploit_django.adapters.django.observation_models import (
    ObservationDBModel,
    ScanRunDBModel,
    get_observation_db,
    initialize_observation_schema,
)
from iotsploit_django.tools.xlogger import xlog

_LOG_NAME = "observation_repository"

# A scan scope is comparable with another only when all of these match. Diffing
# across different scopes would report everything outside the narrower scope as
# having disappeared.
COMPARABLE_SCOPE_FIELDS = ("component_id", "source", "scope_key")


class ObservationPersistenceError(RuntimeError):
    """Recording observations failed.

    Callers should log this and carry on: a persistence failure must never change
    or mask the plugin's own result.
    """


class ObservationRepository:
    def __init__(self, db=None):
        self._db = db or get_observation_db()
        self._session_factory = self._db.SessionLocal

    # ---------------- write path ----------------

    def start_scan(
        self,
        *,
        target_id: str,
        source: str,
        scope_key: str,
        run_id: Optional[str] = None,
        component_id: Optional[str] = None,
    ) -> str:
        """Record that a scan scope is starting; return its ``scan_id``.

        The row is written *before* execution so that a crash leaves evidence the
        scan was attempted rather than looking like it never ran.
        """
        scan_id = uuid.uuid4().hex
        session = self._session_factory()
        try:
            session.add(
                ScanRunDBModel(
                    scan_id=scan_id,
                    run_id=run_id or scan_id,
                    target_id=target_id,
                    component_id=component_id,
                    source=source,
                    scope_key=scope_key,
                    status=ScanStatus.RUNNING.value,
                    is_complete=False,
                    facts_count=0,
                    started_at=datetime.now(),
                )
            )
            session.commit()
            return scan_id
        except SQLAlchemyError as exc:
            session.rollback()
            raise ObservationPersistenceError(f"could not start scan for target '{target_id}': {exc}") from exc
        finally:
            session.close()

    def start_scans(
        self,
        *,
        run_id: str,
        target_id: str,
        source: str,
        scopes: List[ObservationScope],
    ) -> List[StartedScan]:
        """Open every declared scope of one run in a single transaction.

        Either the whole run is recorded as started or none of it is, so a
        partially-opened run can never be mistaken for scopes that were skipped.
        """
        started: List[StartedScan] = []
        session = self._session_factory()
        try:
            for scope in scopes:
                scan_id = uuid.uuid4().hex
                session.add(
                    ScanRunDBModel(
                        scan_id=scan_id,
                        run_id=run_id,
                        target_id=target_id,
                        component_id=scope.component_id,
                        source=source,
                        scope_key=scope.scope_key,
                        status=ScanStatus.RUNNING.value,
                        is_complete=False,
                        facts_count=0,
                        started_at=datetime.now(),
                    )
                )
                started.append(StartedScan(scan_id=scan_id, scope=scope))
            session.commit()
            return started
        except SQLAlchemyError as exc:
            session.rollback()
            raise ObservationPersistenceError(f"could not start scans for target '{target_id}': {exc}") from exc
        finally:
            session.close()

    def complete_scan(self, scan_id: str, facts: Iterable[Fact], *, is_complete: bool = True) -> int:
        """Append every fact and mark the scan succeeded, in one transaction.

        All-or-nothing: if any fact is rejected, none are stored and the scan is
        marked ``persistence_failed`` rather than left looking successful but empty.
        An empty ``facts`` is normal and meaningful -- it is a successful snapshot
        that found nothing.
        """
        facts = list(facts)
        observed_at = datetime.now()
        session = self._session_factory()
        try:
            scan = session.get(ScanRunDBModel, scan_id)
            if scan is None:
                raise ObservationPersistenceError(f"unknown scan_id '{scan_id}'")

            for fact in facts:
                session.add(
                    ObservationDBModel(
                        scan_id=scan_id,
                        protocol=fact.protocol,
                        subject_kind=fact.subject_kind,
                        subject_id=fact.subject_id,
                        observed_property=fact.observed_property,
                        value=fact.value,
                        observed_at=observed_at,
                    )
                )

            scan.status = ScanStatus.SUCCEEDED.value
            scan.is_complete = is_complete
            scan.facts_count = len(facts)
            scan.completed_at = observed_at
            session.commit()
            xlog.info(f"Scan {scan_id} recorded {len(facts)} facts", name=_LOG_NAME)
            return len(facts)
        except SQLAlchemyError as exc:
            session.rollback()
            self._mark_persistence_failed(scan_id, str(exc))
            raise ObservationPersistenceError(f"could not record facts for scan '{scan_id}': {exc}") from exc
        finally:
            session.close()

    def fail_scan(self, scan_id: str, error_summary: Optional[str] = None) -> None:
        """Mark a scan failed. Failed scans never define current state."""
        self._set_terminal_status(scan_id, ScanStatus.FAILED, error_summary)

    def _mark_persistence_failed(self, scan_id: str, error_summary: str) -> None:
        self._set_terminal_status(scan_id, ScanStatus.PERSISTENCE_FAILED, error_summary)

    def _set_terminal_status(self, scan_id: str, status: ScanStatus, error_summary: Optional[str]) -> None:
        session = self._session_factory()
        try:
            scan = session.get(ScanRunDBModel, scan_id)
            if scan is None:
                xlog.warning(f"Cannot set status on unknown scan '{scan_id}'", name=_LOG_NAME)
                return
            scan.status = status.value
            scan.is_complete = False
            scan.completed_at = datetime.now()
            # Bounded: full tracebacks belong in the log, not the database.
            scan.error_summary = (error_summary or "")[:500] or None
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            xlog.error(f"Could not set status '{status.value}' on scan '{scan_id}': {exc}", name=_LOG_NAME)
        finally:
            session.close()

    # ---------------- read path ----------------

    def current(
        self,
        target_id: str,
        *,
        component_id: Optional[str] = None,
        source: Optional[str] = None,
        include_samples: bool = False,
    ) -> List[ObservationRecord]:
        """Latest successful state per comparable scope.

        By default only ``is_complete=True`` snapshots define current state.
        When ``include_samples=True``, newer succeeded ``is_complete=False``
        sample scans (e.g. timed CAN captures) are merged additively on top of
        the latest complete snapshot without ever clearing baseline facts.
        """
        records, _ = self.current_with_scans(
            target_id,
            component_id=component_id,
            source=source,
            include_samples=include_samples,
        )
        return records

    def current_with_scans(
        self,
        target_id: str,
        *,
        component_id: Optional[str] = None,
        source: Optional[str] = None,
        include_samples: bool = False,
    ) -> tuple[List[ObservationRecord], List[ScanSummary]]:
        """Return ``(observations, active_scans)`` for ``target_id``."""
        session = self._session_factory()
        try:
            query = (
                session.query(ScanRunDBModel)
                .filter(
                    ScanRunDBModel.target_id == target_id,
                    ScanRunDBModel.status == ScanStatus.SUCCEEDED.value,
                )
                .order_by(ScanRunDBModel.completed_at.desc(), ScanRunDBModel.scan_id.desc())
            )
            if not include_samples:
                query = query.filter(ScanRunDBModel.is_complete.is_(True))
            if component_id is not None:
                query = query.filter(ScanRunDBModel.component_id == component_id)
            if source is not None:
                query = query.filter(ScanRunDBModel.source == source)

            # Ordered newest-first. For each comparable scope we keep:
            # - the newest complete snapshot (stops further history walk), plus
            # - any newer sample scans (is_complete=False) to merge additively.
            baseline_by_scope: dict[tuple, ScanRunDBModel] = {}
            samples_by_scope: dict[tuple, list[ScanRunDBModel]] = {}
            for scan in query.all():
                key = tuple(getattr(scan, field) for field in COMPARABLE_SCOPE_FIELDS)
                if key in baseline_by_scope:
                    continue
                if scan.is_complete:
                    baseline_by_scope[key] = scan
                elif include_samples:
                    samples_by_scope.setdefault(key, []).append(scan)

            active_scans: dict[str, ScanRunDBModel] = {}
            scope_keys = list(dict.fromkeys([*baseline_by_scope.keys(), *samples_by_scope.keys()]))
            summaries: list[ScanSummary] = []

            for key in scope_keys:
                baseline = baseline_by_scope.get(key)
                samples = samples_by_scope.get(key, [])
                if baseline is not None:
                    active_scans[baseline.scan_id] = baseline
                for sample in samples:
                    active_scans[sample.scan_id] = sample
                # Report the newest scan for this scope in scan summaries.
                head = samples[0] if samples else baseline
                if head is not None:
                    summaries.append(
                        ScanSummary(
                            scan_id=head.scan_id,
                            source=head.source,
                            scope_key=head.scope_key,
                            component_id=head.component_id,
                            is_complete=bool(head.is_complete),
                            facts_count=int(head.facts_count or 0),
                            completed_at=head.completed_at,
                        )
                    )

            if not active_scans:
                return [], summaries

            rows = (
                session.query(ObservationDBModel)
                .filter(ObservationDBModel.scan_id.in_(list(active_scans)))
                .order_by(
                    ObservationDBModel.protocol,
                    ObservationDBModel.subject_kind,
                    ObservationDBModel.subject_id,
                    ObservationDBModel.observed_property,
                )
                .all()
            )
            rows_by_scan: dict[str, list[ObservationDBModel]] = {}
            for row in rows:
                rows_by_scan.setdefault(row.scan_id, []).append(row)

            merged: list[ObservationRecord] = []
            for key in scope_keys:
                baseline = baseline_by_scope.get(key)
                samples = samples_by_scope.get(key, [])
                # Merge oldest -> newest so newer sample measurements refresh
                # matching facts without clearing baseline facts.
                ordered_scans: list[ScanRunDBModel] = []
                if baseline is not None:
                    ordered_scans.append(baseline)
                ordered_scans.extend(reversed(samples))

                by_fact_key: dict[tuple, ObservationRecord] = {}
                for scan in ordered_scans:
                    for row in rows_by_scan.get(scan.scan_id, ()):
                        fact_key = (
                            row.protocol,
                            row.subject_kind,
                            row.subject_id,
                            row.observed_property,
                        )
                        by_fact_key[fact_key] = self._to_record(row, scan)
                merged.extend(by_fact_key.values())

            merged.sort(
                key=lambda r: (
                    r.protocol,
                    r.subject_kind,
                    r.subject_id or "",
                    r.observed_property,
                )
            )
            return merged, summaries
        finally:
            session.close()

    @staticmethod
    def _to_record(row: ObservationDBModel, scan: ScanRunDBModel) -> ObservationRecord:
        return ObservationRecord(
            scan_id=row.scan_id,
            target_id=scan.target_id,
            component_id=scan.component_id,
            source=scan.source,
            scope_key=scan.scope_key,
            protocol=row.protocol,
            subject_kind=row.subject_kind,
            subject_id=row.subject_id,
            observed_property=row.observed_property,
            value=row.value,
            observed_at=row.observed_at,
            is_complete=bool(scan.is_complete),
        )


__all__ = [
    "ObservationPersistenceError",
    "ObservationRepository",
    "initialize_observation_schema",
]
