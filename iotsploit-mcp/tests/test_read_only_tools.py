"""The read-only tool that reads back observations.

Covers the one piece of logic in it: MCP has no way to express "argument
absent", so empty strings stand in for it, and an empty string reaching Django
as `?source=` would filter for a source named "" and always return nothing.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.tools.read_only import register_read_only_tools

pytestmark = pytest.mark.contract


class FakeClient:
    """Records gets and returns an empty result."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.posts: list[str] = []

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((path, params or {}))
        return {"status": "success", "observations": []}

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        self.posts.append(path)
        return {"status": "success"}


def call(client: FakeClient, tool: str, **kwargs) -> Any:
    mcp = FastMCP("test")
    register_read_only_tools(mcp, client_factory=lambda: client)
    return asyncio.run(mcp.call_tool(tool, kwargs))


def test_observations_are_readable_over_mcp():
    """Writing facts an agent cannot read back would be half a capability."""
    client = FakeClient()

    call(client, "get_current_observations", target_id="zxd")

    assert client.calls[0] == ("/api/get_current_observations/", {"target_id": "zxd"})


def test_an_unset_filter_is_omitted_rather_than_sent_empty():
    client = FakeClient()

    call(client, "get_current_observations", target_id="zxd", source="", protocol="can")

    _, params = client.calls[0]
    assert params == {"target_id": "zxd", "protocol": "can"}


def test_every_filter_travels_when_given():
    client = FakeClient()

    call(
        client,
        "get_current_observations",
        target_id="zxd",
        component_id="c_gateway",
        source="agent:claude",
        protocol="tcp",
        subject_kind="port",
    )

    _, params = client.calls[0]
    assert params["component_id"] == "c_gateway"
    assert params["source"] == "agent:claude"
    assert params["subject_kind"] == "port"


@pytest.mark.parametrize(
    ("tool", "arguments", "path"),
    [
        ("scan_devices", {"driver_name": "all"}, "/api/scan_all_devices/"),
        ("scan_devices", {"driver_name": "can driver"}, "/api/scan_device/can%20driver/"),
        ("list_devices", {}, "/api/list_devices/"),
    ],
)
def test_device_discovery_uses_authenticated_post_routes(tool: str, arguments: dict[str, str], path: str):
    client = FakeClient()

    call(client, tool, **arguments)

    assert client.posts == [path]
