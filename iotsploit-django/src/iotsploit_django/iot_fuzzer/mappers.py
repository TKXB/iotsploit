"""DTO/ORM mapping for IoT Fuzzer (Django ring).

Stage-3: placeholder module so later refactors have a stable home for:
- ORM model <-> response payload mapping
- ORM model <-> iosploit_fuzzer DTO mapping (when fuzzer core is introduced)

For now, views still use dict payloads and migrated Django models.
"""

from __future__ import annotations

from typing import Any


def identity(payload: Any) -> Any:
    """Temporary helper for phased migration; will be replaced by real mappers."""

    return payload


