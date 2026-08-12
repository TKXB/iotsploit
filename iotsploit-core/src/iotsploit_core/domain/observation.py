"""Domain models for target observations.

An observation is one fact measured off a device by a scanning tool. Facts are
append-only and always carry provenance (which scan, which tool, when), so that
"what changed since the last scan" stays answerable.

Fact identity is expressed as *fields*, never as a packed dotted string, so it can
be filtered and joined in SQL. See docs/target_data_model_plan.md section 5.3.

This module must stay free of persistence and Django imports.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, JsonValue, model_validator

# subject_kind for facts about the target or component itself rather than about
# some addressable thing on it (a DID, a port, a CAN message).
SUBJECT_SELF = "self"


class ScanStatus(str, Enum):
    """Lifecycle of one scan scope.

    Only ``SUCCEEDED`` together with ``is_complete`` may define current state or
    disappearance: a failed scan must never look like "everything vanished".
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PERSISTENCE_FAILED = "persistence_failed"
    ABANDONED = "abandoned"


class Fact(BaseModel):
    """One observed property of one subject, plus its value.

    ``subject_id`` must already be in canonical form for its protocol (the same
    form the reference catalog stores), otherwise reconciliation silently misses
    matches: "0x123" and "123" are different strings.
    """

    protocol: str = Field(min_length=1, max_length=32)
    subject_kind: str = Field(min_length=1, max_length=32)
    subject_id: Optional[str] = Field(default=None, max_length=128)
    observed_property: str = Field(min_length=1, max_length=64)
    value: JsonValue = None

    @model_validator(mode="after")
    def _check_subject_identity(self) -> "Fact":
        if self.subject_kind == SUBJECT_SELF:
            if self.subject_id is not None:
                raise ValueError(f"subject_id must be None when subject_kind is '{SUBJECT_SELF}'")
        elif not self.subject_id:
            raise ValueError(f"subject_id is required when subject_kind is '{self.subject_kind}'")
        return self

    @property
    def identity(self) -> tuple:
        """The tuple that makes this fact unique within a scan."""
        return (self.protocol, self.subject_kind, self.subject_id, self.observed_property)

    @property
    def display_key(self) -> str:
        """Human-readable key for logs and UI. Derived — never parse this back."""
        parts = [self.protocol, self.subject_kind]
        if self.subject_id is not None:
            parts.append(self.subject_id)
        parts.append(self.observed_property)
        return ".".join(parts)


class ObservationScope(BaseModel):
    """The population one scan covers.

    Two scans are comparable only when their scope matches, which is what stops
    a fast scan from reporting everything outside its range as disappeared.
    ``scope_key`` must never contain credentials -- it is stored and displayed.
    """

    scope_key: str = Field(min_length=1, max_length=128)
    component_id: Optional[str] = None

    @property
    def identity(self) -> tuple:
        return (self.component_id, self.scope_key)


class ObservationBatch(BaseModel):
    """The complete result of one plugin scan scope.

    ``is_complete`` means these facts are the whole snapshot for the declared
    scope. An incomplete batch is kept as history but may not clear prior state.
    """

    scope_key: str = Field(min_length=1, max_length=128)
    component_id: Optional[str] = None
    facts: List[Fact] = Field(default_factory=list)
    is_complete: bool = True

    @property
    def scope(self) -> ObservationScope:
        return ObservationScope(scope_key=self.scope_key, component_id=self.component_id)


class StartedScan(BaseModel):
    """A scan row that exists and is waiting for its result."""

    scan_id: str
    scope: ObservationScope


class ObservationRecord(BaseModel):
    """A stored fact together with the provenance of the scan that produced it."""

    scan_id: str
    target_id: str
    component_id: Optional[str]
    source: str
    scope_key: str
    protocol: str
    subject_kind: str
    subject_id: Optional[str]
    observed_property: str
    value: JsonValue
    observed_at: datetime

    @property
    def display_key(self) -> str:
        parts = [self.protocol, self.subject_kind]
        if self.subject_id is not None:
            parts.append(self.subject_id)
        parts.append(self.observed_property)
        return ".".join(parts)
