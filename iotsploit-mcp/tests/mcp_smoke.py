#!/usr/bin/env python3
"""Smoke test for the IoTSploit MCP streamable-HTTP endpoint.

Connects to a running `iotsploit-mcp http` server, runs the MCP `initialize`
handshake and lists the registered tools. This is a pure connectivity check and
does not require the Django backend to be up. Pass `--call-tool <name>` to also
invoke one read-only tool end-to-end (that path does require Django).

Usage:
    # start the server in another terminal first:
    #   iotsploit-mcp http --host 127.0.0.1 --port 9900
    python iotsploit-mcp/tests/mcp_smoke.py
    python iotsploit-mcp/tests/mcp_smoke.py --url http://127.0.0.1:9900/mcp/
    python iotsploit-mcp/tests/mcp_smoke.py --call-tool system_health

Exit code is 0 on success and 1 on failure, so it is usable in CI.
"""

import argparse
import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = os.getenv("IOTSPLOIT_MCP_URL", "http://127.0.0.1:9900/mcp/")


async def run_smoke(url: str, call_tool: str | None) -> int:
    try:
        async with streamablehttp_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                server = init.serverInfo
                print(f"[ok] initialize: {server.name} v{server.version} (protocol {init.protocolVersion})")

                tools = (await session.list_tools()).tools
                if not tools:
                    print("[fail] server reported zero tools")
                    return 1
                print(f"[ok] list_tools: {len(tools)} tools")
                print("      " + ", ".join(t.name for t in tools))

                if call_tool:
                    result = await session.call_tool(call_tool, {})
                    if result.isError:
                        print(f"[fail] call_tool {call_tool!r} returned an error: {result.content}")
                        return 1
                    text = ""
                    for block in result.content:
                        text = getattr(block, "text", "") or text
                        if text:
                            break
                    print(f"[ok] call_tool {call_tool!r}: {text[:200]}")
    except Exception as exc:  # noqa: BLE001 - smoke test surfaces any failure
        print(f"[fail] {type(exc).__name__}: {exc}")
        print(f"       is `iotsploit-mcp http` running and reachable at {url} ?")
        return 1

    print("PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the IoTSploit MCP HTTP endpoint")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"MCP endpoint URL (default: {DEFAULT_URL})")
    parser.add_argument("--call-tool", default=None, metavar="NAME",
                        help="Also invoke this read-only tool with no arguments (needs Django backend)")
    args = parser.parse_args()

    sys.exit(asyncio.run(run_smoke(args.url, args.call_tool)))


if __name__ == "__main__":
    main()
