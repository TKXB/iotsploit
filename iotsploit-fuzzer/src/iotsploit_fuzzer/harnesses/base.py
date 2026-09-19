from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class HarnessResult:
    ok: bool
    crashed: bool = False
    response: Optional[bytes] = None
    info: Optional[str] = None
    timeout: bool = False
    error: Optional[str] = None
    #: Where the result came from, when the harness can say: ``file:line`` for
    #: an escaped exception. Reported, never compared -- a line number moves
    #: under any edit.
    site: Optional[str] = None


class ProtocolHarness(abc.ABC):
    """Abstract base class for protocol harnesses."""

    @abc.abstractmethod
    def execute(self, payload: bytes) -> HarnessResult:
        """Encode, send and receive based on *payload*.""" 