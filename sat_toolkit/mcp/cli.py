#!/usr/bin/env python3
"""
CLI for SAT Toolkit MCP Server

This script provides a command-line interface to run and test the MCP server.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sat_toolkit.mcp.server import SATMCPServer, main as server_main
from sat_toolkit.mcp.resources import ResourceProvider
from sat_toolkit.mcp.tools import ToolHandler
from sat_toolkit.mcp.adapters import DeviceAdapter, TargetAdapter, ExploitAdapter, SecurityAdapter

def setup_logging(level: str = "INFO"):
    """Setup logging configuration"""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('sat_mcp_server.log')
        ]
    )

async def test_resources():
    """Test resource provider functionality"""
    print("Testing Resource Provider...")
    
    try:
        provider = ResourceProvider()
        resources = provider.get_available_resources()
        
        print(f"Available resources: {len(resources)}")
        for resource in resources:
            print(f"  - {resource.name}: {resource.description}")
        
        # Test reading a few resources
        test_uris = [
            "sat://devices/list",
            "sat://targets/current", 
            "sat://security/status"
        ]
        
        for uri in test_uris:
            try:
                content = provider.get_resource_content(uri)
                print(f"\n--- Resource: {uri} ---")
                print(content.text[:500] + "..." if len(content.text) > 500 else content.text)
            except Exception as e:
                print(f"Error reading {uri}: {e}")
                
    except Exception as e:
        print(f"Error testing resources: {e}")

async def test_tools():
    """Test tool handler functionality"""
    print("\nTesting Tool Handler...")
    
    try:
        handler = ToolHandler()
        tools = handler.get_available_tools()
        
        print(f"Available tools: {len(tools)}")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
        
        # Test a safe tool
        print("\n--- Testing get_system_status tool ---")
        result = handler.execute_tool("get_system_status", {})
        for content in result:
            print(content.text)
            
    except Exception as e:
        print(f"Error testing tools: {e}")

async def test_adapters():
    """Test adapter functionality"""
    print("\nTesting Adapters...")
    
    try:
        # Test Device Adapter
        print("--- Device Adapter ---")
        device_adapter = DeviceAdapter()
        devices = device_adapter.get_available_devices()
        print(f"Found {len(devices)} devices")
        
        driver_states = device_adapter.get_driver_states()
        print(f"Driver states: {len(driver_states)} drivers")
        
        # Test Target Adapter
        print("\n--- Target Adapter ---")
        target_adapter = TargetAdapter()
        current_target = target_adapter.get_current_target()
        print(f"Current target: {current_target.get('name') if current_target else 'None'}")
        
        all_targets = target_adapter.get_all_targets()
        print(f"Total targets: {len(all_targets)}")
        
        # Test Exploit Adapter
        print("\n--- Exploit Adapter ---")
        exploit_adapter = ExploitAdapter()
        exploits = exploit_adapter.get_available_exploits()
        print(f"Available exploits: {len(exploits)}")
        
        # Test Security Adapter
        print("\n--- Security Adapter ---")
        security_adapter = SecurityAdapter()
        status = security_adapter.get_security_status()
        print(f"Security status: {status}")
        
    except Exception as e:
        print(f"Error testing adapters: {e}")

async def run_server():
    """Run the MCP server"""
    print("Starting SAT Toolkit MCP Server...")
    print("The server will run in stdio mode for MCP client communication.")
    print("Press Ctrl+C to stop the server.")
    
    try:
        await server_main()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}")

async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="SAT Toolkit MCP Server CLI")
    parser.add_argument(
        "command",
        choices=["run", "test-resources", "test-tools", "test-adapters", "test-all"],
        help="Command to execute"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    if args.command == "run":
        await run_server()
    elif args.command == "test-resources":
        await test_resources()
    elif args.command == "test-tools":
        await test_tools()
    elif args.command == "test-adapters":
        await test_adapters()
    elif args.command == "test-all":
        await test_adapters()
        await test_resources()
        await test_tools()

if __name__ == "__main__":
    asyncio.run(main()) 