"""Projecting a stored target down to what a listing needs.

A target imported from a production DBC is mostly bulk: the VW MQB fixture is
673 kB, of which 1321 CAN signals are ~99%. A listing that shows a name, a type
and a component count has no use for any of it, and sending it anyway is what
made opening the targets page a multi-megabyte request.

The rule here is deliberately protocol-agnostic. Core does not know what a
``messages`` list is, so it does not name one: **a facet field holding a list or
a mapping is bulk and is omitted, and its size is reported separately.** That is
the same line the UI already draws when it renders a structured facet value as
"35 entries" rather than trying to fit it in a row.

A summarized target is not a target. It is missing data, so it must never be
written back -- ``summary: True`` is on every row so that a caller can tell, and
the full object is one ``get_target`` away.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

#: Marks a projected row. Present and true only on summaries.
SUMMARY_FLAG = "summary"


def _is_bulk(value: Any) -> bool:
    """Whether a facet field holds structure rather than a single value."""
    return isinstance(value, (list, dict))


def _summarize_facets(facets: Any) -> tuple[Dict[str, Any], Dict[str, Dict[str, int]]]:
    """Split one component's facets into scalar fields and the sizes of the rest.

    Unregistered facets are summarized exactly like registered ones: their
    payload is stored verbatim and may be just as large, and core has no way to
    tell the difference anyway.
    """
    kept: Dict[str, Any] = {}
    sizes: Dict[str, Dict[str, int]] = {}
    if not isinstance(facets, Mapping):
        return kept, sizes

    for key, payload in facets.items():
        if not isinstance(payload, Mapping):
            kept[str(key)] = payload
            continue
        scalars = {f: v for f, v in payload.items() if not _is_bulk(v)}
        bulk = {f: len(v) for f, v in payload.items() if _is_bulk(v)}
        kept[str(key)] = scalars
        if bulk:
            sizes[str(key)] = bulk
    return kept, sizes


def summarize_component(component: Mapping[str, Any]) -> Dict[str, Any]:
    """One component with its facet bulk replaced by sizes.

    Subclass fields (``adb_serial_id`` and friends) are scalars and survive:
    dropping them would break the device screens that read them off the listing.
    """
    facets, sizes = _summarize_facets(component.get("facets"))
    row = {k: v for k, v in component.items() if k not in ("facets", "properties")}
    row["facets"] = facets
    if sizes:
        row["facet_sizes"] = sizes
    # Properties are free-form and unbounded; a count is enough for a listing.
    properties = component.get("properties")
    row["property_count"] = len(properties) if isinstance(properties, Mapping) else 0
    return row


def summarize_target(target: Mapping[str, Any]) -> Dict[str, Any]:
    """A target listing row: identity, topology shape, and counts.

    Buses keep their identity but lose ``properties``, which is where a DBC
    import parks the frames that name no sending node -- bulk by any other name.
    """
    components: List[Any] = list(target.get("components") or [])
    buses: List[Any] = list(target.get("buses") or [])
    edges: List[Any] = list(target.get("edges") or [])

    summarized = [summarize_component(c) for c in components if isinstance(c, Mapping)]
    # How many bulk items were left behind, across every facet of every
    # component. For a DBC-imported target this is the frame count.
    omitted = sum(
        count
        for row in summarized
        for fields in (row.get("facet_sizes") or {}).values()
        for count in fields.values()
    )

    row = {k: v for k, v in target.items() if k not in ("components", "buses", "edges")}
    row["components"] = summarized
    row["buses"] = [
        {k: v for k, v in b.items() if k != "properties"} for b in buses if isinstance(b, Mapping)
    ]
    row["edges"] = edges
    row["component_count"] = len(summarized)
    row["bus_count"] = len(row["buses"])
    row["edge_count"] = len(edges)
    row["facet_item_count"] = omitted
    row[SUMMARY_FLAG] = True
    return row
