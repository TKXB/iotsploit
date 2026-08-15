"""The CAN facet, shipped beside the code that consumes it.

Core registers no protocol facets, so this lives here rather than in
iotsploit-core, exactly like ``doip_facet``.

A word on what belongs in it. The bulk of a production DBC -- every message on
a platform, with every signal -- is a *definition*: it describes a car model,
not the bench unit in front of you. Definitions belong in the reference catalog
(plan Plane B), which does not exist yet. What this facet holds is the curated
slice: the frames one component on *this* target actually speaks, on a named
bus. That is small enough to sit in a JSON column and specific enough to be
worth editing per target.

It is not a place to park a two-thousand-signal production DBC. That copy would
be rewritten on every target save, would carry no version and no provenance,
and would go stale the moment the real DBC was corrected.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from iotsploit_core.domain.facet import Facet, register_facet

FACET_KEY = "can"

# Same convention as the DoIP facet: the number is stored as an int so that
# "0x097", "97" and 151 cannot become three different keys, and the facet --
# not core, and not the UI -- declares that humans read it as hex.
HEX = {"format": "hex"}


class CanSignal(BaseModel):
    """One field packed into a frame's data bytes.

    The layout fields mirror what a DBC ``SG_`` line states, because that is
    the only description of a signal anyone actually has. ``factor`` and
    ``offset`` convert the raw integer to engineering units:
    ``physical = raw * factor + offset``.
    """

    name: str
    start_bit: int
    length: int
    # "little" is DBC's @1 (Intel), "big" is @0 (Motorola). Spelled out because
    # a bare 0/1 in stored JSON is unreadable a year later.
    byte_order: str = "little"
    signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    # None means the DBC did not state a range. See ``dbc.parse_dbc``.
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    # The multiplexer token: "M" for the switch signal, "m<n>" for a signal
    # only present when the switch reads <n>. None for ordinary signals.
    multiplexer: Optional[str] = None


class CanMessage(BaseModel):
    """One frame.

    ``frame_id`` and ``is_extended`` together identify a frame: 0x123 standard
    and 0x123 extended are different frames on the same wire, so the flag is
    part of the identity rather than a display hint.
    """

    frame_id: int = Field(json_schema_extra=HEX)
    name: str
    dlc: int = 0
    is_extended: bool = False
    signals: List[CanSignal] = Field(default_factory=list)


@register_facet(FACET_KEY)
class CanFacet(Facet):
    """What one component speaks on one CAN bus.

    ``bus_id`` points at a :class:`~iotsploit_core.domain.target.Bus` on the
    same target. It is not validated here -- a facet cannot see the target it
    hangs off -- so the load-bearing topology claim stays the ``bus_member``
    edge, which *is* validated. This field says which bus the frames belong to
    when several are configured.
    """

    bus_id: str
    # The DBC node name this was imported from, kept so a re-import can find
    # its own rows again after the component has been renamed.
    node: Optional[str] = None
    messages: List[CanMessage] = Field(default_factory=list)
