#!/usr/bin/env python3
"""
Simplified WebSocket Bridge for SAT FastMCP Server

Bridge listens on ws://host:port (default 0.0.0.0:9998) and proxies messages to a
FastMCP stdio subprocess.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from typing import Optional, Set

import websockets


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SATMCPWebSocketBridge:
    """Bridge between WebSocket clients and FastMCP stdio server."""

    def __init__(self, *, host: str = "0.0.0.0", port: int = 9998):
        self.host = host
        self.port = port
        self.mcp_process: Optional[subprocess.Popen] = None
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.mcp_initialized = False
        self.request_id = 0

    async def start_mcp_server(self) -> bool:
        """Start the FastMCP stdio server process."""
        try:
            logger.info("Starting FastMCP server (stdio) via python -m iotsploit_mcp.cli stdio")
            self.mcp_process = subprocess.Popen(
                [sys.executable, "-m", "iotsploit_mcp.cli", "stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
            )
            logger.info("FastMCP server started with PID: %s", self.mcp_process.pid)
            # Important: initialize immediately. Some environments may behave as if stdin is EOF
            # unless a first line is promptly written.
            await self.initialize_mcp_session()

            # Give the process a brief moment; if it still exits, surface stderr for debugging.
            await asyncio.sleep(0.1)
            rc = self.mcp_process.poll()
            if rc is not None:
                try:
                    stderr = self.mcp_process.stderr.read() if self.mcp_process.stderr else ""
                except Exception:
                    stderr = ""
                logger.error("FastMCP server process terminated immediately (rc=%s). stderr=%r", rc, stderr[:2000])
                return False

            return True
        except Exception as e:
            logger.error("Failed to start MCP server: %s", e)
            return False

    async def initialize_mcp_session(self) -> None:
        try:
            logger.info("Initializing MCP session...")
            initialize_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "SAT-WebSocket-Bridge", "version": "1.0.0"},
                },
                "id": "init",
            }
            await self.send_to_mcp(initialize_request)

            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=5.0,
            )

            if response_line:
                response = json.loads(response_line.strip())
                if response.get("id") == "init" and "result" in response:
                    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
                    await self.send_to_mcp(initialized_notification)
                    self.mcp_initialized = True
                    logger.info("MCP session initialized successfully")
                else:
                    logger.error("MCP initialization failed: %s", response)
            else:
                logger.error("No response to MCP initialize request")
        except Exception as e:
            logger.error("Failed to initialize MCP session: %s", e)

    async def send_to_mcp(self, data: dict) -> None:
        try:
            message = json.dumps(data) + "\n"
            assert self.mcp_process is not None and self.mcp_process.stdin is not None
            self.mcp_process.stdin.write(message)
            self.mcp_process.stdin.flush()
        except Exception as e:
            logger.error("Error sending to MCP: %s", e)

    async def handle_client(self, websocket):
        client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        try:
            logger.info("New client connected: %s", client_addr)
            self.clients.add(websocket)
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    if msg_type == "mcp_call_tool":
                        await self.handle_tool_call(data, websocket)
                    elif msg_type == "mcp_list_tools":
                        await self.handle_list_tools(websocket)
                    else:
                        await websocket.send(json.dumps({"type": "error", "error": f"Unknown message type: {msg_type}"}))
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "error": "Invalid JSON format"}))
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client %s disconnected", client_addr)
        except Exception as e:
            logger.error("Error handling client %s: %s", client_addr, e)
        finally:
            self.clients.discard(websocket)

    async def handle_tool_call(self, data: dict, websocket) -> None:
        try:
            if not self.mcp_initialized:
                await websocket.send(json.dumps({"type": "error", "error": "MCP not initialized"}))
                return

            tool_name = data.get("tool_name")
            arguments = data.get("arguments", {})
            if not tool_name:
                await websocket.send(json.dumps({"type": "error", "error": "Missing tool_name"}))
                return

            self.request_id += 1
            request_id = f"req_{self.request_id}"

            params = {"name": tool_name}
            if arguments:
                params["arguments"] = arguments

            mcp_request = {"jsonrpc": "2.0", "method": "tools/call", "params": params, "id": request_id}
            await self.send_to_mcp(mcp_request)

            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=30.0,
            )

            if response_line:
                mcp_response = json.loads(response_line.strip())
                if "result" in mcp_response:
                    await websocket.send(
                        json.dumps({"type": "tool_result", "tool_name": tool_name, "result": mcp_response["result"]})
                    )
                else:
                    await websocket.send(
                        json.dumps(
                            {"type": "tool_error", "tool_name": tool_name, "error": mcp_response.get("error", "Unknown error")}
                        )
                    )
            else:
                await websocket.send(json.dumps({"type": "tool_error", "tool_name": tool_name, "error": "No response from MCP server"}))
        except asyncio.TimeoutError:
            await websocket.send(json.dumps({"type": "tool_error", "tool_name": tool_name, "error": "Tool execution timeout"}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "tool_error", "tool_name": tool_name, "error": str(e)}))

    async def handle_list_tools(self, websocket) -> None:
        try:
            if not self.mcp_initialized:
                await websocket.send(json.dumps({"type": "error", "error": "MCP not initialized"}))
                return

            self.request_id += 1
            request_id = f"req_{self.request_id}"
            mcp_request = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": request_id}
            await self.send_to_mcp(mcp_request)

            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=10.0,
            )
            if response_line:
                mcp_response = json.loads(response_line.strip())
                if "result" in mcp_response:
                    await websocket.send(json.dumps({"type": "tools_list", "tools": mcp_response["result"].get("tools", [])}))
                else:
                    await websocket.send(json.dumps({"type": "error", "error": mcp_response.get("error", "Unknown error")}))
            else:
                await websocket.send(json.dumps({"type": "error", "error": "No response from MCP server"}))
        except asyncio.TimeoutError:
            await websocket.send(json.dumps({"type": "error", "error": "List tools timeout"}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "error": str(e)}))

    async def start_server(self) -> None:
        logger.info("Starting WebSocket bridge on %s:%s", self.host, self.port)
        if not await self.start_mcp_server():
            logger.error("Failed to start MCP server")
            return
        try:
            async with websockets.serve(self.handle_client, self.host, self.port):
                logger.info("WebSocket bridge running on ws://%s:%s", self.host, self.port)
                await asyncio.Future()
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        logger.info("Cleaning up...")
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                await asyncio.sleep(1)
                if self.mcp_process.poll() is None:
                    self.mcp_process.kill()
                logger.info("FastMCP server stopped")
            except Exception as e:
                logger.error("Error stopping MCP server: %s", e)


async def main() -> None:
    bridge = SATMCPWebSocketBridge()
    try:
        await bridge.start_server()
    finally:
        await bridge.cleanup()


if __name__ == "__main__":
    asyncio.run(main())


