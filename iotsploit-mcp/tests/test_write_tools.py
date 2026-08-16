"""The MCP tools that change a target.

These check the shape of what reaches Django, not Django itself: the HTTP
client is a stand-in that records the call. What matters here is that the
whole model goes over the wire -- buses and edges included -- and that a
refusal comes back as a payload rather than an exception, because a tool that
raises tells the agent nothing it can act on.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.adapters.django_http_client import DjangoHttpError
from iotsploit_mcp.tools.write import register_write_tools

pytestmark = pytest.mark.contract


class FakeClient:
    """Records posts. Raises whatever it was told to, like the real one does."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error = error

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((path, json or {}))
        if self.error is not None:
            raise self.error
        return {"status": "success"}


def tools(client: FakeClient) -> dict[str, Any]:
    mcp = FastMCP("test")
    register_write_tools(mcp, client_factory=lambda: client)
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def call(client: FakeClient, tool: str, **kwargs) -> Any:
    """`tool` rather than `name`, which is an argument of the tool itself."""
    mcp = FastMCP("test")
    register_write_tools(mcp, client_factory=lambda: client)
    return asyncio.run(mcp.call_tool(tool, kwargs))


def test_the_surface_is_create_edit_and_select(monkeypatch):
    """Deletion is absent on purpose. It is the one that is not recoverable."""
    assert set(tools(FakeClient())) == {"create_target", "edit_target", "select_target"}


def test_create_sends_the_topology(monkeypatch):
    client = FakeClient()

    call(
        client,
        "create_target",
        target_id="t1",
        name="Bench",
        type="router",
        components=[{"component_id": "c1", "name": "SoC", "type": "generic"}],
        buses=[{"bus_id": "b1", "name": "LAN", "type": "ethernet"}],
        edges=[{"source": "c1", "target": "b1", "relation": "bus_member"}],
    )

    path, payload = client.calls[0]
    assert path == "/api/create_target/"
    assert payload["buses"][0]["bus_id"] == "b1"
    assert payload["edges"][0]["relation"] == "bus_member"


def test_create_defaults_topology_to_empty_rather_than_omitting_it(monkeypatch):
    """Django reads these keys; leaving them out would rely on its defaults."""
    client = FakeClient()

    call(client, "create_target", target_id="t1", name="Bench")

    _, payload = client.calls[0]
    assert payload["buses"] == [] and payload["edges"] == []
    assert payload["components"] == [] and payload["properties"] == {}


def test_edit_passes_updates_through_untouched(monkeypatch):
    client = FakeClient()
    updates = {"buses": [{"bus_id": "b2", "name": "WAN", "type": "ethernet"}]}

    call(client, "edit_target", target_id="t1", updates=updates)

    path, payload = client.calls[0]
    assert path == "/api/edit_target/"
    assert payload == {"target_id": "t1", "updates": updates}


def test_select_posts_the_id(monkeypatch):
    client = FakeClient()

    call(client, "select_target", target_id="t1")

    assert client.calls[0] == ("/api/select_target/", {"target_id": "t1"})


def test_a_refusal_comes_back_as_a_payload_the_agent_can_read(monkeypatch):
    """A raising tool tells the agent nothing. The 400 and its reason do."""
    client = FakeClient(
        error=DjangoHttpError("HTTP 400", status_code=400,
                              response_text='{"error": "Invalid target: edge ... unknown source"}')
    )

    result = call(client, "create_target", target_id="t1", name="Bench")

    text = str(result)
    assert "400" in text
    assert "unknown source" in text
