"""The SOME/IP facet, shipped beside the client that consumes it.

Core registers no protocol facets (``iotsploit_core.domain.facet``), so this
lives with ``SomeIpClient`` rather than in core, exactly like ``doip_facet`` and
``can_facet``.

Three fields, and the omissions are the interesting part.

**No host.** A component already carries an address, and ``target.py`` already
resolves one three different ways -- the wart that facets exist to remove. A
fourth place to write an address would not add capability, it would add a
"which one wins" question. Address resolution lives in exactly one function, in
the Django binding layer.

**No service catalogue.** A list of services and their methods is a *vendor
description* (ARXML/FIBEX), and per ``can_facet``'s docstring that belongs in
the reference catalog, not in a JSON column that gets rewritten on every target
save. The same argument that keeps a 2000-signal DBC out of ``CanFacet`` keeps
a service catalogue out of this one.

**No SD multicast group.** That describes an Ethernet segment, not a component:
every component on the segment repeats the same value. It belongs on a ``Bus``
once buses can carry facets. Until then it is a plugin parameter, which is
honest about being segment-wide rather than pretending to be per-component.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from iotsploit_core.domain.facet import Facet, register_facet

FACET_KEY = "someip"

# Same convention as the DoIP and CAN facets: the number is stored as an int so
# "0x1234", "1234" and 4660 cannot become three different keys, and the facet --
# not core, and not the UI -- declares that humans read it as hex.
HEX = {"format": "hex"}


@register_facet(FACET_KEY)
class SomeipFacet(Facet):
    """How to reach one component's SOME/IP endpoint.

    ``client_id`` identifies *this tester* to the ECU. It is configuration
    rather than a constant because two testers on one bus must not share one,
    and a collision shows up as responses being delivered to the wrong client.
    """

    port: Optional[int] = None
    # "tcp" or "udp". Spelled out rather than a bool, because a third transport
    # is not unthinkable and a bool would have to be renamed to add one.
    transport: str = "tcp"
    client_id: Optional[int] = Field(default=None, json_schema_extra=HEX)


def canonical_service_id(service_id: int, instance_id: int) -> str:
    """The string form of a service instance, as an observation's ``subject_id``.

    Fixed here rather than at each call site for the reason ``canonical_frame_id``
    gives in ``can_facet``: reconciliation joins on this string, and a mismatch
    does not fail loudly -- it silently matches nothing, which reads as "the
    catalog knows nothing about this service".

    Uppercase hex, four digits each, service first:
    ``canonical_service_id(0x1234, 1) == "1234:0001"``. That is the form
    ``docs/target_data_model_plan.md`` uses for SOME/IP subject ids.
    """
    return f"{service_id:04X}:{instance_id:04X}"
