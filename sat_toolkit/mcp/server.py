#!/usr/bin/env python3
"""
MCP Server for SAT Toolkit

This module implements the Model Context Protocol (MCP) server for the SAT Toolkit,
providing LLMs with access to device management, exploit execution, and security assessment capabilities.
"""

import asyncio
import logging
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, CallToolRequest, GetResourceRequest, ListResourcesRequest, ListToolsRequest
)

from .resources import ResourceProvider
from .tools import ToolHandler
from .security import SecurityManager

logger = logging.getLogger(__name__)

class SATMCPServer:
    """MCP Server for SAT Toolkit"""
    
    def __init__(self):
        self.server = Server("sat-toolkit")
        self.resource_provider = ResourceProvider()
        self.tool_handler = ToolHandler()
        self.security_manager = SecurityManager()
        
        # Register handlers
        self._register_handlers()
        
        logger.info("SAT Toolkit MCP Server initialized")
    
    def _register_handlers(self):
        """Register MCP protocol handlers"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available resources"""
            try:
                resources = self.resource_provider.get_available_resources()
                logger.debug(f"Listed {len(resources)} resources")
                return resources
            except Exception as e:
                logger.error(f"Error listing resources: {e}")
                return []
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read a specific resource"""
            try:
                content = self.resource_provider.get_resource_content(uri)
                logger.debug(f"Read resource: {uri}")
                return content.text
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}")
                return f"Error reading resource {uri}: {str(e)}"
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools"""
            try:
                tools = self.tool_handler.get_available_tools()
                logger.debug(f"Listed {len(tools)} tools")
                return tools
            except Exception as e:
                logger.error(f"Error listing tools: {e}")
                return []
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent | ImageContent | EmbeddedResource]:
            """Execute a tool"""
            try:
                arguments = arguments or {}
                
                # Log the tool execution attempt
                logger.info(f"Executing tool: {name} with arguments: {arguments}")
                
                # Check security permissions
                if not self.security_manager.is_operation_allowed(name, "safe"):
                    # For dangerous operations, check if confirmation is provided
                    if name in ["execute_dangerous_exploit", "flash_device_firmware"]:
                        if not arguments.get("confirmation", False):
                            return [TextContent(
                                type="text",
                                text=f"Tool '{name}' requires explicit confirmation. Add 'confirmation': true to proceed."
                            )]
                    else:
                        return [TextContent(
                            type="text",
                            text=f"Tool '{name}' is not allowed by security policy"
                        )]
                
                # Execute the tool
                result = self.tool_handler.execute_tool(name, arguments)
                logger.info(f"Tool {name} executed successfully")
                return result
                
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(
                    type="text",
                    text=f"Error executing tool {name}: {str(e)}"
                )]
    
    async def run(self):
        """Run the MCP server"""
        logger.info("Starting SAT Toolkit MCP Server...")
        
        # Initialize the server with options
        init_options = InitializationOptions(
            server_name="sat-toolkit",
            server_version="1.0.0",
            capabilities={
                "resources": {},
                "tools": {},
                "logging": {}
            }
        )
        
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    init_options
                )
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise

async def main():
    """Main entry point for the MCP server"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run the server
    server = SATMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main()) 