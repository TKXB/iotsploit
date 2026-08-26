"""Errors the CAN catalogue and codec raise.

Two types, split the way :mod:`iotsploit_protocols.errors` splits its three:
by what the caller can do about it.

``CanDefinitionError``  the target is wrong -- fix the ARXML, DBC, or facet.
``CanValueError``       the operator's input is wrong -- fix the value.

The difference is not cosmetic. A definition error means no value would have
worked and the form should say so once, at the top; a value error belongs
against the signal row that caused it, which is why it carries a field map.

Transport failures are deliberately absent. The house rule in
:mod:`iotsploit_protocols.errors` is that a connection failure stays
``OSError`` rather than being re-spelled. ``python-can`` does not follow it: a
SocketCAN interface that is down surfaces as ``can.CanOperationError``, which
is not an ``OSError``, so :mod:`iotsploit_protocols.canbus.socketcan` wraps it
in ``CanTransportError`` rather than let a caller's ``except OSError`` miss it.
"""

from __future__ import annotations

from typing import Dict, Optional

from iotsploit_protocols.errors import ProtocolError


class CanDefinitionError(ProtocolError):
    """The target cannot describe the requested frame.

    Covers absent, ambiguous, conflicting, and unsupported definitions. The
    caller cannot fix any of them by changing a signal value, which is what
    separates this from :class:`CanValueError`.
    """


class CanValueError(ProtocolError):
    """A supplied signal value is missing, unknown, or out of range.

    ``field_errors`` maps a dotted path (``signals.VehicleSpeed``) to a message
    about that one field, so an editor can put the text next to the input that
    caused it instead of showing one opaque failure for the whole frame.
    """

    def __init__(self, message: str, field_errors: Optional[Dict[str, str]] = None) -> None:
        self.field_errors: Dict[str, str] = dict(field_errors or {})
        super().__init__(message)
