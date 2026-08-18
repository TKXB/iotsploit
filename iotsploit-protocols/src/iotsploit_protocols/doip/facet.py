"""The DoIP facet, shipped beside the client that consumes it.

Moved here from ``iotsploit_django.tools.doip_facet``: core deliberately
registers no protocol facets, and a facet belongs with the code that reads it.
The lookup helpers that used to live alongside this class did not come with it
-- they read the current target through Django, so they stayed in the binding
adapter. What is left is the part that is genuinely about DoIP.

The addresses this replaces were class constants on ``DoIP_Mgr``, which meant
adding a vehicle was a code edit. With a facet on the ECU component it is a
target edit.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from iotsploit_core.domain.facet import Facet, register_facet

FACET_KEY = "doip"

# Stored as an int, written and read by humans as hex. An editor that only knew
# the JSON type would make you type 4113 for an address every document in the
# field calls 0x1011. The facet that knows the convention declares it; core
# stays ignorant of what any protocol's numbers mean.
HEX = {"format": "hex"}

# Same idea for uniqueness. A logical address identifies one ECU, so two of them
# on one address is a fault worth showing; a CAN facet's bus_id is a reference to
# something shared and every component on a segment repeats it. Nothing in JSON
# Schema tells those apart, and a view that guessed from the field name would
# flag correct configuration as broken.
HEX_UNIQUE = {"format": "hex", "unique": True}


@register_facet(FACET_KEY)
class DoipFacet(Facet):
    """DoIP/UDS addressing for one ECU.

    ``logical_address`` is an int on purpose: it is the join key to the
    reference catalog, and "0x1011", "1011" and 4113 must not be three different
    keys. Secrets are deliberately absent -- PINs stay in ClassifiedInfo/Env_Mgr
    rather than being copied into a JSON column.
    """

    logical_address: int = Field(json_schema_extra=HEX_UNIQUE)
    tester_address: int = Field(default=0x0E80, json_schema_extra=HEX)
    host: Optional[str] = None
    port: int = 13400
