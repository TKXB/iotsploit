"""The tools that change or act on a target, and record what was seen on it.

Kept apart from ``read_only`` on purpose. That module's read-only-ness is a
property worth being able to point at, not an accident of what happened to be
written first, and separating the two makes "what can an agent change?" a
question answered by an import rather than by reading two hundred lines.

Deletion is deliberately absent. Creating and editing a target is recoverable
-- the previous values are in the payload the agent already read -- and
deleting one is not. Add it here when something needs it, with whatever
confirmation that need implies.

``record_observations`` is a different kind of write from the other three. Those
change configuration, which is a human's claim about what a device is; that one
records evidence, which is a claim that something was actually seen. The backend
keeps the two kinds of claim apart by assigning the source itself, so an agent's
finding is durable without being able to pass for a plugin's measurement.
"""

from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.adapters.django_http_client import DjangoHttpClient
from iotsploit_mcp.tools.read_only import _call

def register_write_tools(
    mcp: FastMCP,
    client_factory: Callable[[], DjangoHttpClient] = DjangoHttpClient.from_env,
) -> None:
    """Register the tools that mutate or act on a target."""

    def client() -> DjangoHttpClient:
        return client_factory()

    @mcp.tool()
    def create_target(
        target_id: str,
        name: str,
        type: str = "generic",
        status: str = "active",
        ip_address: Optional[str] = None,
        location: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
        components: Optional[list[dict[str, Any]]] = None,
        buses: Optional[list[dict[str, Any]]] = None,
        edges: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Create a target, including its topology.

        `type` is one of the keys from get_target_types (vehicle, ecu, iot,
        phone, router, camera, generic). A component may carry `facets`, keyed
        by the facet names get_facet_schemas publishes; a key no plugin defines
        is stored verbatim rather than rejected.

        buses and edges are the topology. An edge's `source` and `target` must
        each name a component_id, a bus_id, or the target_id itself -- the
        backend refuses the write with a 400 naming the endpoint it could not
        resolve, so put components and buses in the same call as the edges
        that reference them.

        Fails with 400 if the target_id is taken.
        """

        def run() -> dict[str, Any]:
            return client().post(
                "/api/create_target/",
                json={
                    "target_id": target_id,
                    "name": name,
                    "type": type,
                    "status": status,
                    "ip_address": ip_address,
                    "location": location,
                    "properties": properties or {},
                    "components": components or [],
                    "buses": buses or [],
                    "edges": edges or [],
                },
            )

        return _call("create_target", run)

    @mcp.tool()
    def edit_target(target_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Replace fields on an existing target.

        `updates` accepts name, type, status, ip_address, location, properties,
        components, buses and edges. Anything else is ignored. Each field is
        replaced wholesale, not merged: sending `components` omits every
        component not in the list, and an edge naming one of those is then
        unresolvable and the whole write is refused with a 400.

        Read the target with get_target first and send it back modified.
        """

        def run() -> dict[str, Any]:
            return client().post(
                "/api/edit_target/",
                json={"target_id": target_id, "updates": updates},
            )

        return _call("edit_target", run)

    @mcp.tool()
    def select_target(target_id: str) -> dict[str, Any]:
        """Make a target the current one, which is what plugins execute against."""

        def run() -> dict[str, Any]:
            return client().post(
                "/api/select_target/", json={"target_id": target_id}
            )

        return _call("select_target", run)

    @mcp.tool()
    def execute_plugin(
        plugin_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an enabled exploit plugin against the current target.

        Call select_target first when the intended target is not already
        current. Plugin parameters come from describe_plugin. Execution may
        interact with attached hardware or the target and may return either a
        synchronous result or an asynchronous task identifier.
        """

        def run() -> dict[str, Any]:
            return client().post(
                "/api/execute_plugin/",
                json={"plugin_name": plugin_name, "parameters": parameters or {}},
            )

        return _call("execute_plugin", run)

    @mcp.tool()
    def record_observations(
        target_id: str,
        agent: str,
        scope_key: str,
        facts: list[dict[str, Any]],
        component_id: Optional[str] = None,
        is_complete: bool = True,
    ) -> dict[str, Any]:
        """Record what you observed on a target, as one scan.

        For findings you produced yourself -- a port you probed, a response you
        read -- rather than by running a plugin. Configuration goes through
        edit_target; this is for evidence.

        Each fact is `{"protocol": ..., "subject_kind": ..., "subject_id": ...,
        "observed_property": ..., "value": ...}`. `subject_kind` is the sort of
        thing observed ("port", "did", "message", "interface") and `subject_id`
        identifies which one, in the canonical form for that protocol -- a CAN
        frame id is uppercase hex zero-padded to 3 digits (8 if extended), so
        "1A0", never "0x1a0", or it silently matches nothing later. Use
        `subject_kind: "self"` with no `subject_id` for a fact about the target
        or component itself. `value` is any JSON.

        `scope_key` names what you actually examined, because `is_complete`
        claims these facts are all of it -- and a later complete scan of the
        same scope records anything now missing as gone. "tcp:22,80,443" is
        honest; "tcp" claims you swept 65535 ports. Pass `is_complete=False`
        if you were interrupted or only spot-checked, which keeps the facts as
        history without letting them define current state.

        An empty `facts` list is a real result, not a no-op: it records that a
        scope was examined and nothing was there.

        You cannot choose your source. It is stored as `agent:<agent>`, so your
        findings never pass for a plugin's; sending a `source` is refused with a
        400 rather than quietly overridden.
        """

        def run() -> dict[str, Any]:
            return client().post(
                "/api/record_observations/",
                json={
                    "target_id": target_id,
                    "agent": agent,
                    "scope_key": scope_key,
                    "component_id": component_id,
                    "is_complete": is_complete,
                    "facts": facts,
                },
            )

        return _call("record_observations", run)
