"""Inspection mode must refuse active scanning at the MCP dispatch boundary."""

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.tools.read_only import register_read_only_tools

pytestmark = pytest.mark.contract


def test_inspection_tools_do_not_register_scan():
    async def scenario():
        server = FastMCP("inspection-test")
        register_read_only_tools(server, read_only=True)

        tools = {tool.name for tool in await server.list_tools()}

        assert {"list_devices", "get_current_target", "list_plugins", "system_health"} <= tools
        assert "scan_devices" not in tools
        with pytest.raises(Exception, match="Unknown tool"):
            await server.call_tool("scan_devices", {})

    asyncio.run(scenario())
