"""SQLAlchemy ORM mappings for the observation domain (adapter layer).

Two tables, deliberately:

- ``scan_runs``   -- one row per plugin scan scope, written *before* execution.
- ``observations`` -- append-only facts belonging to a scan.

A facts-only table could not represent a successful scan that found nothing, which
is exactly how "no internal IPs are exposed" must be recorded.

This module owns its own declarative ``Base``: ``get_default_sqlalchemy_db()``
builds a fresh engine/session/Base on every call, so these tables are *not*
registered in the target metadata and must be created explicitly at startup.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import declarative_base

from iotsploit_django.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db

Base = declarative_base()


class ScanRunDBModel(Base):
    __tablename__ = "scan_runs"

    scan_id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False)
    component_id = Column(String, nullable=True)
    source = Column(String, nullable=False)
    scope_key = Column(String, nullable=False)
    status = Column(String, nullable=False)
    is_complete = Column(Boolean, default=False, nullable=False)
    facts_count = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_summary = Column(String, nullable=True)

    __table_args__ = (
        # Supports "latest successful complete scan per comparable scope".
        Index(
            "ix_scan_current",
            "target_id",
            "component_id",
            "source",
            "scope_key",
            "status",
            "is_complete",
            "completed_at",
        ),
        Index("ix_scan_run", "target_id", "run_id"),
    )


class ObservationDBModel(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String, ForeignKey("scan_runs.scan_id", ondelete="CASCADE"), nullable=False)
    protocol = Column(String, nullable=False)
    subject_kind = Column(String, nullable=False)
    subject_id = Column(String, nullable=True)  # NULL when subject_kind == "self"
    observed_property = Column(String, nullable=False)
    value = Column(JSON, nullable=False)
    observed_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "scan_id",
            "protocol",
            "subject_kind",
            "subject_id",
            "observed_property",
            name="uq_observation_identity",
        ),
        Index("ix_observation_scan", "scan_id"),
        # Cross-target queries: "which targets expose DID F190?"
        Index("ix_observation_subject", "protocol", "subject_kind", "subject_id"),
    )


def enable_sqlite_foreign_keys(engine) -> None:
    """SQLite ignores foreign keys unless asked per connection.

    Without this the ON DELETE CASCADE above is silently a no-op and deleting a
    scan leaves its observations orphaned.
    """

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_default_db = None


def get_observation_db():
    """Return (and memoize) the default database for observations."""
    global _default_db
    if _default_db is None:
        db = get_default_sqlalchemy_db()
        enable_sqlite_foreign_keys(db.engine)
        _default_db = db
    return _default_db


def initialize_observation_schema(db=None):
    """Create both tables if absent. Idempotent; safe to call on every startup."""
    db = db or get_observation_db()
    Base.metadata.create_all(db.engine)
    return db
