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

logger = logging.getLogger("sat_fastmcp")
logger.setLevel(logging.INFO)

# Add file logging for debugging (since this runs as subprocess)
file_logger = logging.getLogger('sat_fastmcp_file')
file_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
log_dir = "/tmp/sat_logs"
os.makedirs(log_dir, exist_ok=True)

# Add file handler
file_handler = logging.FileHandler(f"{log_dir}/sat_fastmcp.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
file_logger.addHandler(file_handler)

if not logger.handlers:
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

def log_both(level, message):
    """Log to both regular logger and file logger"""
    getattr(logger, level)(message)
    getattr(file_logger, level)(message)

# Initialize FastMCP server
mcp = FastMCP("sat-toolkit")

# Initialize core components (Django is accessed via HTTP API only)
device_manager = None
try:
    from iotsploit_mcp.composition_root import build_device_manager

    device_manager = build_device_manager()
    log_both("info", "SAT MCP components initialized (driver states via Django HTTP API)")
except Exception as e:
    log_both("warning", f"SAT MCP components failed to initialize: {e}")

@mcp.tool()
async def scan_devices(driver_name: str = "all") -> str:
    """Scan for available devices"""
    try:
        if not device_manager:
            return "Device manager not available"
        
        log_both('info', f"Scanning devices (driver: {driver_name})")
        
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
        log_both('error', f"Error scanning devices: {e}")
        return f"Error scanning devices: {str(e)}"

@mcp.tool()
async def get_system_status() -> str:
    """Get overall system status"""
    try:
        log_both('info', "Getting system status")
        
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
        log_both('error', f"Error getting system status: {e}")
        return f"Error getting system status: {str(e)}"

@mcp.tool()
async def read_serial_port(port: str = "/dev/ttyUSB0", baudrate: int = 115200, timeout: int = 300, auto_interact: bool = True) -> str:
    """Read and analyze serial port output using AI-powered pattern detection"""
    try:
        # Import the plugin
        import sys
        import os
        plugin_path = os.path.join(project_root, "plugins", "exploits", "serial")
        if plugin_path not in sys.path:
            sys.path.append(plugin_path)
        
        from picocom_serial_reader import PicocomSerialReaderPlugin
        
        # Initialize plugin
        plugin = PicocomSerialReaderPlugin()
        plugin.initialize()
        
        # Execute serial reading
        parameters = {
            'port': port,
            'baudrate': baudrate,
            'timeout': timeout,
            'auto_interact': auto_interact,
            'analyze_output': True
        }
        
        log_both('info', f"Reading serial port {port} (baudrate: {baudrate}, timeout: {timeout}s)")
        result = await plugin.execute_async(target=None, parameters=parameters)
        
        if result.status:
            # Format the response for AI consumption
            analysis_data = result.data.get('analysis', {})
            report = result.data.get('report', 'No report generated')
            
            log_both('info', f"Result message: {result.message}")
            response = {
                "success": True,
                "message": result.message,
                "analysis": {
                    "device_type": analysis_data.get('device_type', 'unknown'),
                    "confidence": analysis_data.get('confidence', 0.0),
                    "login_detected": analysis_data.get('login_detected', False),
                    "shell_type": analysis_data.get('shell_type', 'unknown'),
                    "output_lines": analysis_data.get('output_lines_count', 0),
                    "detected_patterns": analysis_data.get('detected_patterns', [])
                },
                "report": report,
                "sample_output": analysis_data.get('raw_output_sample', [])
            }
            
            log_both('info', "Serial port reading completed successfully")
            return json.dumps(response, indent=2)
        else:
            log_both('error', f"Serial port reading failed: {result.message}")
            return json.dumps({
                "success": False,
                "error": result.message,
                "data": result.data
            }, indent=2)
            
    except Exception as e:
        log_both('error', f"Error reading serial port: {e}")
        return json.dumps({
            "success": False,
            "error": f"Error reading serial port: {str(e)}"
        }, indent=2)

@mcp.tool()
async def list_serial_ports() -> str:
    """List available serial ports on the system"""
    try:
        log_both('info', "Listing serial ports")
        
        import serial.tools.list_ports
        
        ports = serial.tools.list_ports.comports()
        port_list = []
        
        for port in ports:
            port_info = {
                "device": port.device,
                "description": port.description,
                "manufacturer": getattr(port, 'manufacturer', 'Unknown'),
                "product": getattr(port, 'product', 'Unknown'),
                "vid": getattr(port, 'vid', None),
                "pid": getattr(port, 'pid', None)
            }
            port_list.append(port_info)
        
        if not port_list:
            return "No serial ports found on the system"
        
        log_both('info', f"Found {len(port_list)} serial ports")
        return json.dumps({
            "success": True,
            "message": f"Found {len(port_list)} serial port(s)",
            "ports": port_list
        }, indent=2)
        
    except Exception as e:
        log_both('error', f"Error listing serial ports: {e}")
        return f"Error listing serial ports: {str(e)}"

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    
    async def main():
        try:
            log_both('info', "Starting SAT FastMCP Server")
            await mcp.run_stdio_async()
        except KeyboardInterrupt:
            log_both('info', "FastMCP Server stopped by user")
        except Exception as e:
            log_both('error', f"FastMCP Server error: {e}")
            sys.exit(1)
    
    asyncio.run(main()) 