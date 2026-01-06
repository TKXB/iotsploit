from __future__ import annotations

import argparse
import asyncio
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iotsploit-mcp")
    sub = p.add_subparsers(dest="cmd")

    ws = sub.add_parser("ws", help="Start WebSocket bridge (default)")
    ws.add_argument("--host", default="0.0.0.0")
    ws.add_argument("--port", type=int, default=9998)

    sub.add_parser("stdio", help="Start FastMCP stdio server (usually started by bridge)")
    return p


async def _run_ws(host: str, port: int) -> None:
    from iotsploit_mcp.websocket_bridge_simple import SATMCPWebSocketBridge

    bridge = SATMCPWebSocketBridge(host=host, port=port)
    await bridge.start_server()


async def _run_stdio() -> None:
    import nest_asyncio

    nest_asyncio.apply()

    from iotsploit_mcp.sat_fastmcp import run_stdio_async

    await run_stdio_async()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = _build_parser()
    args = p.parse_args(argv)

    cmd = args.cmd or "ws"  # default: ws
    if cmd == "ws":
        asyncio.run(_run_ws(host=args.host, port=args.port))
        return
    if cmd == "stdio":
        asyncio.run(_run_stdio())
        return

    p.error(f"Unknown cmd: {cmd}")


if __name__ == "__main__":
    main()

