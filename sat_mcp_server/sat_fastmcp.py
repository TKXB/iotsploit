#!/usr/bin/env python3
"""
SAT FastMCP Server

A simplified MCP server for SAT Toolkit using FastMCP
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("sat-toolkit")

# Initialize SAT components
try:
    from sat_toolkit.core.device_manager import DeviceDriverManager
    device_manager = DeviceDriverManager()
    logger.info("SAT components initialized successfully")
except Exception as e:
    logger.warning(f"SAT components failed to initialize: {e}")
    device_manager = None

@mcp.tool()
async def scan_devices(driver_name: str = "all") -> str:
    """Scan for available devices"""
    try:
        if not device_manager:
            return "Device manager not available"
        
        if driver_name == "all":
            enabled_drivers = [
                driver for driver in device_manager.list_drivers() 
                if device_manager.is_driver_enabled(driver)
            ]
            
            if not enabled_drivers:
                return "No enabled device drivers found"
            
            all_results = []
            for driver in enabled_drivers:
                try:
                    devices = device_manager.scan_devices(driver)
                    device_list = [
                        f"  - {device.get('name', 'Unknown')}: {device.get('status', 'Unknown')}"
                        for device in devices
                    ]
                    if device_list:
                        all_results.append(f"Driver '{driver}':\n" + "\n".join(device_list))
                    else:
                        all_results.append(f"Driver '{driver}': No devices found")
                except Exception as e:
                    all_results.append(f"Driver '{driver}': Error - {str(e)}")
            
            return "\n\n".join(all_results) if all_results else "No devices found"
        else:
            devices = device_manager.scan_devices(driver_name)
            if devices:
                device_list = [
                    f"- {device.get('name', 'Unknown')}: {device.get('status', 'Unknown')}"
                    for device in devices
                ]
                return f"Found {len(devices)} devices:\n" + "\n".join(device_list)
            else:
                return f"No devices found using driver '{driver_name}'"
                
    except Exception as e:
        logger.error(f"scan_devices error: {e}")
        return f"Error scanning devices: {str(e)}"

@mcp.tool()
async def get_system_status() -> str:
    """Get overall system status"""
    try:
        status = {
            "timestamp": asyncio.get_event_loop().time(),
            "device_manager_available": device_manager is not None
        }
        
        if device_manager:
            enabled_drivers = [
                driver for driver in device_manager.list_drivers() 
                if device_manager.is_driver_enabled(driver)
            ]
            status["enabled_drivers"] = len(enabled_drivers)
            status["total_drivers"] = len(device_manager.list_drivers())
        
        return json.dumps(status, indent=2)
        
    except Exception as e:
        logger.error(f"get_system_status error: {e}")
        return f"Error getting system status: {str(e)}"

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    
    async def main():
        try:
            logger.info("Starting SAT FastMCP Server...")
            await mcp.run_stdio_async()
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            sys.exit(1)
    
    asyncio.run(main()) 