"""The tools that change a target.

Kept apart from ``read_only`` on purpose. That module's read-only-ness is a
property worth being able to point at, not an accident of what happened to be
written first, and separating the two makes "what can an agent change?" a
question answered by an import rather than by reading two hundred lines.

Deletion is deliberately absent. Creating and editing a target is recoverable
-- the previous values are in the payload the agent already read -- and
deleting one is not. Add it here when something needs it, with whatever
confirmation that need implies.
"""

from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.adapters.django_http_client import DjangoHttpClient
from iotsploit_mcp.tools.read_only import _call

def register_write_tools(
    mcp: FastMCP,
    client_factory: Callable[[], DjangoHttpClient] = DjangoHttpClient.from_env,
) -> None:
    """Register the tools that create, edit and select a target."""

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
