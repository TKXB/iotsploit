"""Errors a protocol client raises.

Three types, not a hierarchy for its own sake. Each one exists because a caller
can do something different about it:

``NotConfigured``   the target is missing settings -- fix the target, not the code.
``NegativeResponse`` the peer answered and said no -- the scan worked, the ECU refused.
``ProtocolError``   everything else that is ours.

Transport failures are *not* wrapped. A connection refused is ``ConnectionError``
and a read timeout is ``TimeoutError``, both stdlib: re-spelling them in a new
namespace buys nothing and forces callers to catch two names for one condition.
"""

from __future__ import annotations

from typing import Optional


class ProtocolError(Exception):
    """Base class for protocol-level failures."""


class NotConfigured(ProtocolError):
    """Required configuration is absent.

    Raised instead of falling back to a built-in address. A helper that guesses
    a host silently probes the wrong device and reports its silence as a
    finding, which is worse than not running.
    """


class NegativeResponse(ProtocolError):
    """The peer replied, and the reply says the request was refused.

    Carries the raw code so a caller can branch on it. ``code`` is the SOME/IP
    return code or the UDS NRC depending on who raised it; ``name`` is the
    protocol's own label for that code when one is known.
    """

    def __init__(self, code: int, name: Optional[str] = None, message: str = "") -> None:
        self.code = code
        self.name = name
        label = name or f"0x{code:02X}"
        super().__init__(message or f"negative response: {label}")
