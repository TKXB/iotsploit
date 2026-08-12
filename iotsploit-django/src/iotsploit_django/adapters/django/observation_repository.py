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

from iotsploit_core.domain.observation import Fact, ObservationRecord, ScanStatus
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
    ) -> List[ObservationRecord]:
        """Latest successful complete snapshot per comparable scope.

        Returns records rather than a flattened dict: if two sources report the
        same subject, both stay visible with their provenance intact. Resolving
        that conflict is a presentation decision, not a silent last-writer-wins.
        """
        session = self._session_factory()
        try:
            query = (
                session.query(ScanRunDBModel)
                .filter(
                    ScanRunDBModel.target_id == target_id,
                    ScanRunDBModel.status == ScanStatus.SUCCEEDED.value,
                    ScanRunDBModel.is_complete.is_(True),
                )
                .order_by(ScanRunDBModel.completed_at.desc(), ScanRunDBModel.scan_id.desc())
            )
            if component_id is not None:
                query = query.filter(ScanRunDBModel.component_id == component_id)
            if source is not None:
                query = query.filter(ScanRunDBModel.source == source)

            # Ordered newest-first, so the first scan seen for a scope is its
            # current one. Small result sets; a window function can replace this
            # if scan counts ever make it matter.
            latest: dict[tuple, ScanRunDBModel] = {}
            for scan in query.all():
                key = tuple(getattr(scan, field) for field in COMPARABLE_SCOPE_FIELDS)
                latest.setdefault(key, scan)

            if not latest:
                return []

            scans = {scan.scan_id: scan for scan in latest.values()}
            rows = (
                session.query(ObservationDBModel)
                .filter(ObservationDBModel.scan_id.in_(list(scans)))
                .order_by(
                    ObservationDBModel.protocol,
                    ObservationDBModel.subject_kind,
                    ObservationDBModel.subject_id,
                    ObservationDBModel.observed_property,
                )
                .all()
            )

            return [self._to_record(row, scans[row.scan_id]) for row in rows]
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
        )


__all__ = [
    "ObservationPersistenceError",
    "ObservationRepository",
    "initialize_observation_schema",
]
