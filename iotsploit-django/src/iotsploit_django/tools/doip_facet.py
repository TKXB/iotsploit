"""Django-side lookup helpers for the DoIP facet.

``DoipFacet`` itself lives in ``iotsploit_protocols.doip.facet`` beside the
client that consumes it; it is re-exported here for existing callers.
"""

from __future__ import annotations

import logging
from typing import Optional

from iotsploit_protocols.doip.facet import FACET_KEY, HEX, HEX_UNIQUE, DoipFacet

logger = logging.getLogger(__name__)

__all__ = ["FACET_KEY", "HEX", "HEX_UNIQUE", "DoipFacet", "doip_facet_for", "logical_address_for"]


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
