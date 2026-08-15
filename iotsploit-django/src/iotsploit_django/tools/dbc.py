"""Reading a DBC file, and folding what it says onto a target.

A DBC describes a network: which nodes exist, which frames each one sends, and
how the bits inside a frame are laid out. That maps onto the target model
without inventing anything new -- a node is a component, the network is a bus,
"this node sends these frames" is a :class:`~can_facet.CanFacet`, and "this
node is on this bus" is a ``bus_member`` edge.

Only the subset that carries meaning is parsed: ``BU_``, ``BO_``, ``SG_`` and
node comments. Attribute definitions (``BA_DEF_``), colours and value tables
are display metadata for DBC editors and are dropped rather than stored as
noise.

There is no dependency on cantools on purpose. This reads a handful of line
shapes; pulling in a full CAN toolchain to do it would be a heavier commitment
than the job needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from iotsploit_django.tools.can_facet import FACET_KEY, CanFacet, CanMessage, CanSignal

#: DBC's literal name for "no node". Frames transmitted by it have no sender.
NO_SENDER = "Vector__XXX"

#: A frame id with bit 31 set is a 29-bit extended id; the rest is the id.
_EXTENDED_FLAG = 0x80000000

_NODES_RE = re.compile(r"^BU_\s*:\s*(.*)$")
_MESSAGE_RE = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\S+)")
_SIGNAL_RE = re.compile(
    r"^\s*SG_\s+(\w+)\s*"
    r"(?:(M|m\d+)\s+)?:\s*"  # multiplexer token, absent on ordinary signals
    r"(\d+)\|(\d+)@([01])([+-])\s*"
    r"\(([^,]*),([^)]*)\)\s*"
    r"\[([^|]*)\|([^\]]*)\]\s*"
    r'"([^"]*)"'
)
_NODE_COMMENT_RE = re.compile(r'^CM_\s+BU_\s+(\w+)\s+"(.*)"\s*;?\s*$')


@dataclass(frozen=True)
class DbcNode:
    """A ``BU_`` entry and the frames it transmits."""

    name: str
    comment: str = ""
    messages: Tuple[CanMessage, ...] = ()


@dataclass
class DbcContents:
    """Everything read out of a DBC that the target model has a home for."""

    nodes: List[DbcNode] = field(default_factory=list)
    #: Frames whose transmitter is ``Vector__XXX``. They belong to the bus
    #: rather than to any component -- see ``apply_dbc``.
    unsent: List[CanMessage] = field(default_factory=list)


def parse_dbc(text: str) -> DbcContents:
    """Parse ``text`` into nodes, frames and signals.

    Faithful about two things a reader is likely to second-guess:

    * ``dlc`` is whatever the file says, even when signals are laid out beyond
      it. Plenty of hand-written DBCs declare 0 and mean 8, but guessing would
      turn a file's mistake into ours.
    * ``[0|0]`` is DBC's idiom for "no range stated", so it becomes ``None``
      rather than a literal range of zero to zero, which would read as a claim
      that the signal is always zero.
    """
    contents = DbcContents()
    declared: List[str] = []
    comments: Dict[str, str] = {}
    # Frames keyed by transmitter, in file order.
    by_sender: Dict[str, List[CanMessage]] = {}
    current: Optional[CanMessage] = None

    for line in text.splitlines():
        nodes = _NODES_RE.match(line)
        if nodes:
            declared = nodes.group(1).split()
            continue

        message = _MESSAGE_RE.match(line)
        if message:
            raw_id = int(message.group(1))
            current = CanMessage(
                frame_id=raw_id & ~_EXTENDED_FLAG,
                name=message.group(2),
                dlc=int(message.group(3)),
                is_extended=bool(raw_id & _EXTENDED_FLAG),
            )
            by_sender.setdefault(message.group(4), []).append(current)
            continue

        signal = _SIGNAL_RE.match(line)
        if signal and current is not None:
            current.signals.append(_signal_from(signal))
            continue

        comment = _NODE_COMMENT_RE.match(line)
        if comment:
            comments[comment.group(1)] = comment.group(2)
            continue

        # A blank line does not end a message block, but any other unmatched
        # top-level keyword does: SG_ lines only ever follow their own BO_.
        if line and not line[0].isspace():
            current = None

    # Declaration order first, then any transmitter the file used without
    # declaring -- a malformed DBC, but its intent is unambiguous.
    #
    # Vector__XXX is dropped even when the BU_ line names it, which real files
    # do: it is the placeholder for "no node", so treating it as one would put
    # every unsent frame on a component *and* on the bus, twice over.
    ordered = [n for n in declared if n != NO_SENDER]
    ordered += [s for s in by_sender if s not in declared and s != NO_SENDER]
    for name in ordered:
        contents.nodes.append(
            DbcNode(
                name=name,
                comment=comments.get(name, ""),
                messages=tuple(by_sender.get(name, ())),
            )
        )
    contents.unsent = list(by_sender.get(NO_SENDER, ()))
    return contents


def _signal_from(match: "re.Match[str]") -> CanSignal:
    minimum = _float(match.group(9))
    maximum = _float(match.group(10))
    if minimum == 0.0 and maximum == 0.0:
        minimum = maximum = None

    return CanSignal(
        name=match.group(1),
        multiplexer=match.group(2),
        start_bit=int(match.group(3)),
        length=int(match.group(4)),
        byte_order="little" if match.group(5) == "1" else "big",
        signed=match.group(6) == "-",
        factor=_float(match.group(7), 1.0),
        offset=_float(match.group(8), 0.0),
        minimum=minimum,
        maximum=maximum,
        unit=match.group(11),
    )


def _float(text: str, fallback: float = 0.0) -> float:
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return fallback


def component_id_for(node: str) -> str:
    """The component id a DBC node imports as.

    Derived rather than random so that re-importing the same file twice lands
    on the same rows instead of duplicating the network.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", node.lower()).strip("_")
    return f"c_{slug or 'node'}"


def apply_dbc(
    target_data: Dict[str, Any],
    dbc_text: str,
    *,
    bus_id: str,
    bus_name: Optional[str] = None,
    component_type: str = "ecu",
) -> Dict[str, Any]:
    """Return ``target_data`` with the DBC's network folded into it.

    One bus, one component per node, one ``bus_member`` edge each, and a
    ``can`` facet per node holding the frames it transmits. Frames with no
    declared transmitter go to ``bus.properties['messages']``: a frame nobody
    is known to send is a fact about the bus, not about any component, and the
    Bus docstring already names the bus as where CAN messages anchor.

    Re-running with the same file is a no-op, and re-running with an updated
    file replaces each node's frames wholesale rather than accumulating stale
    ones. Both matter because there is no import bookkeeping anywhere else.

    The argument is not modified.
    """
    contents = parse_dbc(dbc_text)
    result = _deep_copy(target_data)

    buses = list(result.get("buses") or [])
    bus = next((b for b in buses if b.get("bus_id") == bus_id), None)
    if bus is None:
        bus = {"bus_id": bus_id, "name": bus_name or bus_id, "type": "can", "properties": {}}
        buses.append(bus)
    elif bus_name:
        bus["name"] = bus_name
    bus.setdefault("properties", {})
    if contents.unsent:
        bus["properties"]["messages"] = [m.model_dump() for m in contents.unsent]
    result["buses"] = buses

    components = list(result.get("components") or [])
    edges = list(result.get("edges") or [])

    for node in contents.nodes:
        component = _component_for(components, node.name)
        if component is None:
            component = {
                "component_id": component_id_for(node.name),
                "name": node.name,
                "type": component_type,
                "status": "active",
                "facets": {},
                "properties": {},
            }
            components.append(component)

        component.setdefault("facets", {})[FACET_KEY] = CanFacet(
            bus_id=bus_id,
            node=node.name,
            messages=list(node.messages),
        ).model_dump()

        if node.comment:
            component.setdefault("properties", {}).setdefault("description", node.comment)

        _add_edge(edges, component["component_id"], bus_id)

    result["components"] = components
    result["edges"] = edges
    return result


def _component_for(components: List[Dict[str, Any]], node: str) -> Optional[Dict[str, Any]]:
    """The row a node imports onto: the one that already claims it, else the id.

    Matching on the stored node name first is what lets someone rename the
    component to something readable without a re-import duplicating it.
    """
    for component in components:
        facet = (component.get("facets") or {}).get(FACET_KEY)
        if isinstance(facet, dict) and facet.get("node") == node:
            return component

    wanted = component_id_for(node)
    for component in components:
        if component.get("component_id") == wanted:
            return component
    return None


def _add_edge(edges: List[Dict[str, Any]], source: str, target: str) -> None:
    for edge in edges:
        if edge.get("source") == source and edge.get("target") == target and edge.get("relation") == "bus_member":
            return
    edges.append({"source": source, "target": target, "relation": "bus_member", "properties": {}})


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
