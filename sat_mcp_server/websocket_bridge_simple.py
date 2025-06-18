#!/usr/bin/env python3
"""
Simplified WebSocket Bridge for SAT FastMCP Server

This bridge allows WebSocket clients (like Flutter UI) to communicate 
with the FastMCP server using stdio protocol.
"""

import asyncio
import json
import logging
import subprocess
import sys
import websockets
from pathlib import Path
from typing import Dict, Optional, Set

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SATMCPWebSocketBridge:
    """Bridge between WebSocket clients and FastMCP server"""
    
    def __init__(self, port: int = 9998):
        self.port = port
        self.mcp_process: Optional[subprocess.Popen] = None
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.mcp_initialized = False
        self.request_id = 0
        
    async def start_mcp_server(self):
        """Start the FastMCP server process"""
        try:
            # Get the path to the sat_fastmcp.py file
            mcp_server_path = Path(__file__).parent / "sat_fastmcp.py"
            
            if not mcp_server_path.exists():
                logger.error(f"FastMCP server not found at: {mcp_server_path}")
                return False
            
            logger.info(f"Starting FastMCP server: {mcp_server_path}")
            
            # Start the MCP server process
            self.mcp_process = subprocess.Popen(
                [sys.executable, str(mcp_server_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0
            )
            
            logger.info(f"FastMCP server started with PID: {self.mcp_process.pid}")
            
            # Wait for server to initialize
            await asyncio.sleep(1)
            
            if self.mcp_process.poll() is not None:
                logger.error("FastMCP server process terminated immediately")
                return False
            
            # Initialize MCP session
            await self.initialize_mcp_session()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            return False
    
    async def initialize_mcp_session(self):
        """Initialize the MCP session"""
        try:
            logger.info("Initializing MCP session...")
            
            # Send initialize request
            initialize_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "SAT-WebSocket-Bridge",
                        "version": "1.0.0"
                    }
                },
                "id": "init"
            }
            
            await self.send_to_mcp(initialize_request)
            
            # Read initialize response
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=5.0
            )
            
            if response_line:
                response = json.loads(response_line.strip())
                logger.info(f"MCP initialize response: {response}")
                
                if response.get("id") == "init" and "result" in response:
                    # Send initialized notification
                    initialized_notification = {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {}
                    }
                    
                    await self.send_to_mcp(initialized_notification)
                    self.mcp_initialized = True
                    logger.info("✅ MCP session initialized successfully")
                else:
                    logger.error(f"MCP initialization failed: {response}")
            else:
                logger.error("No response to MCP initialize request")
                
        except Exception as e:
            logger.error(f"Failed to initialize MCP session: {e}")
    
    async def send_to_mcp(self, data: dict):
        """Send data to MCP server stdin"""
        try:
            message = json.dumps(data) + "\n"
            self.mcp_process.stdin.write(message)
            self.mcp_process.stdin.flush()
        except Exception as e:
            logger.error(f"Error sending to MCP: {e}")
    
    async def handle_client(self, websocket):
        """Handle a WebSocket client connection"""
        try:
            client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
            logger.info(f"New client connected: {client_addr}")
            self.clients.add(websocket)
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"Received from {client_addr}: {data}")
                    
                    # Handle different message types
                    msg_type = data.get('type')
                    
                    if msg_type == 'mcp_call_tool':
                        await self.handle_tool_call(data, websocket)
                    elif msg_type == 'mcp_list_tools':
                        await self.handle_list_tools(websocket)
                    elif msg_type == 'ai_query':
                        await self.handle_ai_query(data, websocket)
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "error": f"Unknown message type: {msg_type}"
                        }))
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {client_addr}: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": "Invalid JSON format"
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_addr} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def handle_tool_call(self, data: dict, websocket):
        """Handle MCP tool call request"""
        try:
            logger.info(f"=== BRIDGE TOOL CALL START ===")
            logger.info(f"Received data: {json.dumps(data, indent=2)}")
            
            if not self.mcp_initialized:
                logger.error("MCP not initialized")
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "MCP not initialized"
                }))
                return
            
            tool_name = data.get('tool_name')
            arguments = data.get('arguments', {})
            
            logger.info(f"Tool name: {tool_name}")
            logger.info(f"Arguments type: {type(arguments)}")
            logger.info(f"Arguments content: {arguments}")
            
            if not tool_name:
                logger.error("Missing tool_name")
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "Missing tool_name"
                }))
                return
            
            # Generate unique request ID
            self.request_id += 1
            request_id = f"req_{self.request_id}"
            logger.info(f"Generated request ID: {request_id}")
            
            # Send MCP tool call request
            params = {"name": tool_name}
            
            # Only include arguments if they're not empty
            if arguments:
                params["arguments"] = arguments
                logger.info(f"Including arguments in MCP request")
            else:
                logger.info(f"Omitting arguments from MCP request (empty)")
            
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": params,
                "id": request_id
            }
            
            logger.info(f"Sending to MCP server: {json.dumps(mcp_request, indent=2)}")
            await self.send_to_mcp(mcp_request)
            logger.info(f"MCP request sent successfully")
            
            # Read MCP response
            logger.info(f"Waiting for MCP server response...")
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=30.0
            )
            
            logger.info(f"MCP server response line: {response_line}")
            
            if response_line:
                mcp_response = json.loads(response_line.strip())
                logger.info(f"MCP tool response: {json.dumps(mcp_response, indent=2)}")
                
                # Send response to client
                if "result" in mcp_response:
                    logger.info(f"Tool execution successful")
                    response_data = {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": mcp_response["result"]
                    }
                    logger.info(f"Sending success response: {json.dumps(response_data, indent=2)}")
                    await websocket.send(json.dumps(response_data))
                else:
                    logger.error(f"Tool execution failed")
                    error_data = {
                        "type": "tool_error",
                        "tool_name": tool_name,
                        "error": mcp_response.get("error", "Unknown error")
                    }
                    logger.info(f"Sending error response: {json.dumps(error_data, indent=2)}")
                    await websocket.send(json.dumps(error_data))
            else:
                logger.error("No response from MCP server")
                await websocket.send(json.dumps({
                    "type": "tool_error",
                    "tool_name": tool_name,
                    "error": "No response from MCP server"
                }))
            
            logger.info(f"=== BRIDGE TOOL CALL END ===")
                
        except asyncio.TimeoutError:
            logger.error(f"Tool execution timeout for {tool_name}")
            await websocket.send(json.dumps({
                "type": "tool_error",
                "tool_name": tool_name,
                "error": "Tool execution timeout"
            }))
        except Exception as e:
            logger.error(f"Error handling tool call: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception details: {repr(e)}")
            await websocket.send(json.dumps({
                "type": "tool_error", 
                "tool_name": tool_name,
                "error": str(e)
            }))
    
    async def handle_list_tools(self, websocket):
        """Handle MCP list tools request"""
        try:
            if not self.mcp_initialized:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "MCP not initialized"
                }))
                return
            
            # Generate unique request ID
            self.request_id += 1
            request_id = f"req_{self.request_id}"
            
            # Send MCP list tools request
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": request_id
            }
            
            await self.send_to_mcp(mcp_request)
            
            # Read MCP response
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.mcp_process.stdout.readline),
                timeout=10.0
            )
            
            if response_line:
                mcp_response = json.loads(response_line.strip())
                logger.info(f"MCP list tools response: {mcp_response}")
                
                # Send response to client
                if "result" in mcp_response:
                    await websocket.send(json.dumps({
                        "type": "tools_list",
                        "tools": mcp_response["result"].get("tools", [])
                    }))
                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": mcp_response.get("error", "Unknown error")
                    }))
            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "No response from MCP server"
                }))
                
        except asyncio.TimeoutError:
            await websocket.send(json.dumps({
                "type": "error",
                "error": "List tools timeout"
            }))
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "error": str(e)
            }))
    
    async def handle_ai_query(self, data: dict, websocket):
        """Handle AI query by providing a simple response for now"""
        try:
            query = data.get('query', '')
            
            # Simple AI response mapping for now
            query_lower = query.lower()
            if 'hello' in query_lower or 'hi' in query_lower:
                response = "Hello! I'm your SAT toolkit assistant. You can ask me to scan devices, check system status, or help with commands."
            elif 'help' in query_lower:
                response = "I can help you with:\n- Scanning devices: 'scan devices'\n- System status: 'system status'\n- Available tools: 'list tools'"
            elif 'device' in query_lower:
                response = "For device operations, try 'scan devices' to see available devices."
            elif 'status' in query_lower:
                response = "For system information, try 'system status' to see the current state."
            else:
                response = f"I understand you want to know about '{query}'. Try using specific commands like 'scan devices' or 'system status' for better results."
            
            await websocket.send(json.dumps({
                "type": "ai_response",
                "message": response
            }))
            
        except Exception as e:
            logger.error(f"Error handling AI query: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "error": str(e)
            }))
    
    async def start_server(self):
        """Start the WebSocket bridge server"""
        logger.info(f"Starting WebSocket bridge on port {self.port}")
        
        # Start the MCP server first
        if not await self.start_mcp_server():
            logger.error("Failed to start MCP server")
            return
        
        try:
            # Start WebSocket server
            async with websockets.serve(self.handle_client, "0.0.0.0", self.port):
                logger.info(f"✅ WebSocket bridge running on ws://0.0.0.0:{self.port}")
                logger.info("Press Ctrl+C to stop the server")
                await asyncio.Future()  # Run forever
                
        except Exception as e:
            logger.error(f"WebSocket server error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")
        
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                await asyncio.sleep(1)
                if self.mcp_process.poll() is None:
                    self.mcp_process.kill()
                logger.info("FastMCP server stopped")
            except Exception as e:
                logger.error(f"Error stopping MCP server: {e}")

async def main():
    """Main entry point"""
    bridge = SATMCPWebSocketBridge()
    
    try:
        await bridge.start_server()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await bridge.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 