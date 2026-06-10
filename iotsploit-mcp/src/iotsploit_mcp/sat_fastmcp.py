#!/usr/bin/env python3
"""SAT FastMCP server.

External agents use the streamable-HTTP transport. The legacy stdio runner remains
for the WebSocket bridge until that UI path is migrated.
"""

import asyncio
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.tools.read_only import register_read_only_tools
from iotsploit_mcp.tools.xlogger_mcp import xlog_mcp

logger = xlog_mcp.get_logger(
    "sat_fastmcp",
    # enable via env IOTSPLOIT_MCP_LOG_TO_FILE=1 (and optionally IOTSPLOIT_MCP_LOG_FILE / IOTSPLOIT_MCP_LOG_DIR)
)


mcp = FastMCP(
    "sat-toolkit",
    host=os.getenv("IOTSPLOIT_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("IOTSPLOIT_MCP_PORT", "9900")),
    streamable_http_path="/mcp",
)
register_read_only_tools(mcp)


@mcp.tool()
async def list_serial_ports() -> str:
    """List available serial ports on the system."""
    try:
        logger.info("Listing serial ports")
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
        port_list = []
        for port in ports:
            port_list.append(
                {
                    "device": port.device,
                    "description": port.description,
                    "manufacturer": getattr(port, "manufacturer", "Unknown"),
                    "product": getattr(port, "product", "Unknown"),
                    "vid": getattr(port, "vid", None),
                    "pid": getattr(port, "pid", None),
                }
            )

        if not port_list:
            return "No serial ports found on the system"
        return json.dumps({"success": True, "ports": port_list}, indent=2)
    except Exception as e:
        logger.error("Error listing serial ports: %s", e)
        return f"Error listing serial ports: {str(e)}"


class BearerTokenMiddleware:
    """Minimal bearer-token guard for the MCP HTTP endpoint."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        expected = f"Bearer {self.token}"
        if headers.get("authorization") == expected:
            await self.app(scope, receive, send)
            return

        body = b'{"status":"error","message":"Missing or invalid bearer token"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


async def run_http_async(*, host: str = "127.0.0.1", port: int = 9900) -> None:
    """Run the streamable-HTTP MCP server at /mcp."""
    token = os.getenv("IOTSPLOIT_MCP_TOKEN")
    if not token:
        raise RuntimeError("IOTSPLOIT_MCP_TOKEN is required for the HTTP MCP endpoint")

    mcp.settings.host = host
    mcp.settings.port = port
    if host not in ("127.0.0.1", "localhost", "::1"):
        # The server is intentionally exposed beyond loopback; rely on bearer token
        # here and TLS/reverse proxy at deployment time.
        mcp.settings.transport_security = None

    import uvicorn

    logger.info("Starting SAT FastMCP Server (streamable HTTP) on %s:%s/mcp", host, port)
    app = BearerTokenMiddleware(mcp.streamable_http_app(), token)
    config = uvicorn.Config(app, host=host, port=port, log_level=mcp.settings.log_level.lower())
    server = uvicorn.Server(config)
    await server.serve()


async def run_stdio_async() -> None:
    """Run FastMCP stdio server (legacy bridge path)."""
    logger.info("Starting SAT FastMCP Server (stdio)")
    await mcp.run_stdio_async()


if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(run_stdio_async())
