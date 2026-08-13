"""The DoIP facet, shipped beside the code that consumes it.

Core deliberately registers no protocol facets, so this lives with DoIP_Mgr
rather than in iotsploit-core. Adding SOME/IP or CAN means another module like
this one, not a core release.

The addresses it replaces were class constants on DoIP_Mgr, which meant adding
a vehicle was a code edit. With a facet configured on the ECU component, it is
a target edit.
"""

from __future__ import annotations

import logging
from typing import Optional

from iotsploit_core.domain.facet import Facet, register_facet

logger = logging.getLogger(__name__)

FACET_KEY = "doip"


@register_facet(FACET_KEY)
class DoipFacet(Facet):
    """DoIP/UDS addressing for one ECU.

    ``logical_address`` is an int on purpose: it is the join key to the
    reference catalog, and "0x1011", "1011" and 4113 must not be three
    different keys. Secrets are deliberately absent -- PINs stay in
    ClassifiedInfo/Env_Mgr rather than being copied into a JSON column.
    """

    logical_address: int
    tester_address: int = 0x0E80
    host: Optional[str] = None
    port: int = 13400


def doip_facet_for(ecu: str) -> Optional[DoipFacet]:
    """The DoIP facet of the current target's component named ``ecu``, or None.

    Returns None whenever anything is missing or not configured, so callers can
    fall back to their previous hardcoded default.
    """
    name = (ecu or "").upper()
    if not name:
        return None
    try:
        from iotsploit_django.adapters.django.target_models import TargetManager

        target = TargetManager.get_instance().get_current_target()
    except Exception as exc:  # pragma: no cover - defensive: no DB, no target
        logger.debug("No current target for DoIP facet lookup: %s", exc)
        return None

    for comp in getattr(target, "components", None) or []:
        if comp.name.upper() != name:
            continue
        facet = comp.facet(FACET_KEY)
        if isinstance(facet, DoipFacet):
            return facet
        if facet is not None:
            # A RawFacet here means the stored payload did not validate.
            logger.warning("Component %r has an unusable %r facet; using the built-in default", comp.name, FACET_KEY)
        return None
    return None


def logical_address_for(ecu: str, default: int) -> int:
    """Configured DoIP address for ``ecu``, or ``default`` when unconfigured."""
    facet = doip_facet_for(ecu)
    if facet is None:
        return default
    logger.debug("Using configured DoIP address 0x%X for %s", facet.logical_address, ecu)
    return facet.logical_address
