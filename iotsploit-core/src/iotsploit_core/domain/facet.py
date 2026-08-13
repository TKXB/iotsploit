"""Facets: composable, protocol-specific configuration on a component.

A DoIP ECU is simultaneously an ECU and a network node. Single inheritance
cannot say that, which is why one attribute currently has several lookup paths.
Facets say it by composition instead: a component carries a dict of small typed
groups, keyed by a short string.

**Core defines the mechanism and ships zero protocol facets.** A fixed set of
DoipFacet/CanFacet classes here would just replace component subclasses with
facet subclasses -- adding a protocol would still mean releasing core. The rule
is that a facet ships with the code that consumes it:

    # beside the DoIP driver, not here
    @register_facet("doip")
    class DoipFacet(Facet):
        logical_address: int

See docs/target_data_model_plan.md section 3.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)


class Facet(BaseModel):
    """One coherent group of settings.

    ``extra="allow"`` so a field written by a newer version of the owning plugin
    survives a round trip through this one.
    """

    model_config = ConfigDict(extra="allow")


class RawFacet(Facet):
    """A facet whose key has no registered type.

    Its payload is preserved verbatim. Without this, uninstalling a plugin --
    or merely not having loaded it yet -- would silently destroy the
    configuration of every target that used it.
    """


class FacetRegistry:
    """Maps a facet key to the class that validates it."""

    _types: Dict[str, Type[Facet]] = {}

    @classmethod
    def register(cls, key: str, facet_cls: Type[Facet]) -> None:
        if not issubclass(facet_cls, Facet):
            raise TypeError(f"{facet_cls!r} is not a Facet subclass")
        existing = cls._types.get(key)
        if existing is not None and existing is not facet_cls:
            logger.warning("Facet key %r re-registered: %s replaces %s", key, facet_cls, existing)
        cls._types[key] = facet_cls

    @classmethod
    def unregister(cls, key: str) -> None:
        """Drop a registration. Data already stored under the key degrades to RawFacet."""
        cls._types.pop(key, None)

    @classmethod
    def registered(cls) -> Dict[str, Type[Facet]]:
        return dict(cls._types)

    @classmethod
    def resolve(cls, key: str, raw: Any) -> Facet:
        """Build the facet for ``key``, never raising and never losing the payload.

        Validation failures degrade to RawFacet rather than rejecting the whole
        component: a stored row that predates a schema change must still load.
        Code that constructs a registered facet directly still gets validation.
        """
        if isinstance(raw, Facet):
            return raw
        if not isinstance(raw, dict):
            raise TypeError(f"Facet {key!r} must be a mapping, got {type(raw).__name__}")

        facet_cls = cls._types.get(key)
        if facet_cls is None:
            return RawFacet(**raw)
        try:
            return facet_cls(**raw)
        except ValidationError as exc:
            logger.warning("Facet %r did not validate as %s, keeping raw: %s", key, facet_cls.__name__, exc)
            return RawFacet(**raw)

    @classmethod
    def schemas(cls) -> Dict[str, Dict[str, Any]]:
        """JSON Schema per registered key, for a schema-driven editor."""
        return {key: facet_cls.model_json_schema() for key, facet_cls in cls._types.items()}


def register_facet(key: str) -> Callable[[Type[Facet]], Type[Facet]]:
    """Class decorator registering a facet class under ``key``."""

    def decorator(facet_cls: Type[Facet]) -> Type[Facet]:
        FacetRegistry.register(key, facet_cls)
        return facet_cls

    return decorator


def resolve_facets(value: Any) -> Optional[Dict[str, Facet]]:
    """Normalize a raw ``facets`` mapping into resolved Facet instances."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"facets must be a mapping, got {type(value).__name__}")
    return {str(key): FacetRegistry.resolve(str(key), raw) for key, raw in value.items()}
