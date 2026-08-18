"""Turn "the TCAM" into a protocol client for the TCAM.

This is the only place that knows both the current target and the protocol
clients, which is the whole point: ``iotsploit_protocols`` stays free of Django
and of any particular vehicle, and everything environment-shaped lives here.

An adapter rather than a tool. ``tools/`` is the legacy drawer -- ``Env_Mgr``,
``Bash_Script_Mgr``, ``DeviceInfo``, singletons with ``Instance()`` -- and this
reads Django models to produce domain values, which is what ``adapters/django/``
is for. It implements no core port, so it does not belong in ``ports_impl/``.

**Address resolution happens once, here.** ``target.py`` already resolves a
component address three ways, and that triplication is exactly what the facet
work is removing; a protocol facet carrying its own ``host`` would make it four.
So no protocol facet stores an address: the order is

1. what the caller passed explicitly,
2. the component's own ``ip_address`` (typed field or ``properties``),
3. otherwise :class:`NotConfigured` -- never a built-in default.

When a ``net`` facet eventually holds the address, this function is the only one
that changes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from iotsploit_protocols.errors import NotConfigured
from iotsploit_protocols.someip import SomeIpClient, SomeIpConfig, SomeipFacet
from iotsploit_protocols.someip.facet import FACET_KEY as SOMEIP_FACET_KEY

logger = logging.getLogger(__name__)


def current_target() -> Optional[Any]:
    """The selected target, or None when there is no database or no selection."""
    try:
        from iotsploit_django.adapters.django.target_models import TargetManager

        return TargetManager.get_instance().get_current_target()
    except Exception as exc:  # pragma: no cover - defensive: no DB, no target
        logger.debug("No current target available: %s", exc)
        return None


def component_named(name: str) -> Optional[Any]:
    """The current target's component called ``name``, matched case-insensitively."""
    wanted = (name or "").upper()
    if not wanted:
        return None
    target = current_target()
    for comp in getattr(target, "components", None) or []:
        if comp.name.upper() == wanted:
            return comp
    return None


def component_address(comp: Any) -> Optional[str]:
    """The component's configured IP, from ``properties`` or a typed field."""
    properties = getattr(comp, "properties", None)
    if isinstance(properties, dict):
        address = properties.get("ip_address")
        if address:
            return str(address)
    address = getattr(comp, "ip_address", None)
    return str(address) if address else None


def typed_facet(comp: Any, key: str, expected: type) -> Optional[Any]:
    """The component's facet under ``key``, only if it validated.

    A ``RawFacet`` here means the stored payload did not match the schema. That
    is worth a warning rather than silent use: reading ``port`` off a raw dict
    would either fail obscurely later or, worse, pick up a stale field.
    """
    facet = comp.facet(key) if hasattr(comp, "facet") else None
    if isinstance(facet, expected):
        return facet
    if facet is not None:
        logger.warning(
            "Component %r has an unusable %r facet; treating it as unconfigured",
            getattr(comp, "name", "?"), key,
        )
    return None


def someip_config_for(
    ecu: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    timeout: float = 5.0,
) -> SomeIpConfig:
    """Build a :class:`SomeIpConfig` for the named component of the current target.

    ``port`` has no fallback. SOME/IP reserves 30490 for service discovery only;
    the port an application endpoint listens on is per-deployment, so guessing
    one would mean probing an arbitrary port and reporting its silence.
    """
    comp = component_named(ecu)
    if comp is None:
        raise NotConfigured(
            f"no component named {ecu!r} on the current target; select a target "
            f"or add the component before calling SOME/IP"
        )

    facet = typed_facet(comp, SOMEIP_FACET_KEY, SomeipFacet)

    resolved_host = host or component_address(comp)
    if not resolved_host:
        raise NotConfigured(
            f"component {ecu!r} has no ip_address configured and no host was passed"
        )

    resolved_port = port or (facet.port if facet else None)
    if not resolved_port:
        raise NotConfigured(
            f"component {ecu!r} has no SOME/IP port configured; set the 'someip' "
            f"facet's port or pass one explicitly"
        )

    return SomeIpConfig(
        host=resolved_host,
        port=int(resolved_port),
        transport=(facet.transport if facet else "tcp"),
        client_id=(facet.client_id if facet and facet.client_id is not None else 0x0001),
        timeout=timeout,
    )


def someip_client_for(
    ecu: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    timeout: float = 5.0,
) -> SomeIpClient:
    """A SOME/IP client aimed at the named component. Use as a context manager."""
    return SomeIpClient(someip_config_for(ecu, host=host, port=port, timeout=timeout))
