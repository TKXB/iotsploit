#!/usr/bin/env python3
"""
SAT FastMCP Server (stdio)

Execution plane: MCP tools call iotsploit-core usecases. All enabled/disabled states
are sourced from Django SSOT over HTTP APIs.
"""

import asyncio
import json
import os

from mcp.server.fastmcp import FastMCP

from iotsploit_mcp.tools.xlogger_mcp import xlog_mcp

# sat_fastmcp runs as a subprocess; allow optional file logging.
logger = xlog_mcp.get_logger(
    "sat_fastmcp",
    # enable via env IOTSPLOIT_MCP_LOG_TO_FILE=1 (and optionally IOTSPLOIT_MCP_LOG_FILE / IOTSPLOIT_MCP_LOG_DIR)
)


mcp = FastMCP("sat-toolkit")


# Lazy-loaded managers (initialized on first use to avoid startup order issues)
_device_manager = None
_exploit_manager = None
_init_attempted = False


def _ensure_managers_initialized() -> tuple:
    """Lazily initialize device/exploit managers on first use.
    
    Returns (device_manager, exploit_manager). Either may be None if Django API is unavailable.
    """
    global _device_manager, _exploit_manager, _init_attempted
    
    if _init_attempted:
        return _device_manager, _exploit_manager
    
    _init_attempted = True
    try:
        from iotsploit_mcp.composition_root import build_device_manager, build_exploit_manager

        _device_manager = build_device_manager()
        _exploit_manager = build_exploit_manager()
        logger.info("SAT MCP components initialized (SSOT via Django HTTP API)")
    except Exception as e:
        logger.error("SAT MCP components failed to initialize: %s", e)
        logger.info("Will retry on next tool call...")
        _init_attempted = False  # Allow retry on next call
    
    return _device_manager, _exploit_manager


def get_device_manager():
    """Get device manager, initializing if needed."""
    dm, _ = _ensure_managers_initialized()
    return dm


def get_exploit_manager():
    """Get exploit manager, initializing if needed."""
    _, em = _ensure_managers_initialized()
    return em


@mcp.tool()
async def scan_devices(driver_name: str = "all") -> str:
    """Scan for available devices."""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            return "Device manager not available. Ensure Django API is running at IOTSPLOIT_DJANGO_API_BASE_URL"

        logger.info("Scanning devices (driver: %s)", driver_name)

        if driver_name == "all":
            enabled_drivers = [
                driver for driver in device_manager.list_drivers() if device_manager.is_driver_enabled(driver)
            ]

            if not enabled_drivers:
                return "No enabled device drivers found"

            all_results = []
            for driver in enabled_drivers:
                try:
                    result = device_manager.scan_devices(driver)
                    if result.get("status") != "success":
                        all_results.append(f"Driver '{driver}': {result.get('message', 'Scan failed')}")
                        continue
                    devices = result.get("devices", [])
                    device_list = [
                        f"  - {getattr(device, 'name', 'Unknown')}: {getattr(device, 'device_type', 'Unknown')}"
                        for device in devices
                    ]
                    if device_list:
                        all_results.append(f"Driver '{driver}':\n" + "\n".join(device_list))
                    else:
                        all_results.append(f"Driver '{driver}': No devices found")
                except Exception as e:
                    all_results.append(f"Driver '{driver}': Error - {str(e)}")

            return "\n\n".join(all_results) if all_results else "No devices found"

        result = device_manager.scan_devices(driver_name)
        if result.get("status") != "success":
            return f"Scan failed: {result.get('message', 'Unknown error')}"
        devices = result.get("devices", [])
        if devices:
            device_list = [f"- {getattr(device, 'name', 'Unknown')}: {getattr(device, 'device_type', 'Unknown')}" for device in devices]
            return f"Found {len(devices)} devices:\n" + "\n".join(device_list)
        return f"No devices found using driver '{driver_name}'"

    except Exception as e:
        logger.error("Error scanning devices: %s", e)
        return f"Error scanning devices: {str(e)}"


@mcp.tool()
async def get_system_status() -> str:
    """Get overall system status."""
    try:
        logger.info("Getting system status")
        device_manager = get_device_manager()
        exploit_manager = get_exploit_manager()
        status = {
            "timestamp": asyncio.get_event_loop().time(),
            "device_manager_available": device_manager is not None,
            "exploit_manager_available": exploit_manager is not None,
        }
        if device_manager:
            enabled_drivers = [
                driver for driver in device_manager.list_drivers() if device_manager.is_driver_enabled(driver)
            ]
            status["enabled_drivers"] = len(enabled_drivers)
            status["total_drivers"] = len(device_manager.list_drivers())
        if exploit_manager:
            status["enabled_exploit_plugins"] = len(exploit_manager.list_plugins())
        return json.dumps(status, indent=2)
    except Exception as e:
        logger.error("Error getting system status: %s", e)
        return f"Error getting system status: {str(e)}"


@mcp.tool()
async def read_serial_port(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 115200,
    timeout: int = 300,
    auto_interact: bool = True,
) -> str:
    """Read and analyze serial port output using exploit plugin system (SSOT mode)."""
    try:
        exploit_manager = get_exploit_manager()
        if not exploit_manager:
            return json.dumps({"success": False, "error": "Exploit manager not available. Ensure Django API is running."}, indent=2)

        parameters = {
            "port": port,
            "baudrate": baudrate,
            "timeout": timeout,
            "auto_interact": auto_interact,
            "analyze_output": True,
        }

        plugin_name = os.getenv("IOTSPLOIT_SERIAL_READER_PLUGIN_NAME", "Picocom Serial Reader")
        logger.info("Executing exploit plugin '%s' for serial port %s", plugin_name, port)
        result = await exploit_manager.execute_plugin_async(plugin_name, target=None, parameters=parameters)

        if result is None:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Plugin '{plugin_name}' not found or disabled in Django SSOT",
                    "available_enabled_plugins": exploit_manager.list_plugins(),
                },
                indent=2,
            )

        if getattr(result, "status", False):
            analysis_data = (result.data or {}).get("analysis", {}) if hasattr(result, "data") else {}
            report = (result.data or {}).get("report", "No report generated") if hasattr(result, "data") else "No report generated"
            return json.dumps(
                {
                    "success": True,
                    "message": getattr(result, "message", ""),
                    "analysis": {
                        "device_type": analysis_data.get("device_type", "unknown"),
                        "confidence": analysis_data.get("confidence", 0.0),
                        "login_detected": analysis_data.get("login_detected", False),
                        "shell_type": analysis_data.get("shell_type", "unknown"),
                        "output_lines": analysis_data.get("output_lines_count", 0),
                        "detected_patterns": analysis_data.get("detected_patterns", []),
                    },
                    "report": report,
                    "sample_output": analysis_data.get("raw_output_sample", []),
                },
                indent=2,
            )

        return json.dumps(
            {
                "success": False,
                "error": getattr(result, "message", "Serial reading failed"),
                "data": getattr(result, "data", None),
            },
            indent=2,
        )

    except Exception as e:
        logger.error("Error reading serial port: %s", e)
        return json.dumps({"success": False, "error": f"Error reading serial port: {str(e)}"}, indent=2)


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


async def run_stdio_async() -> None:
    """Run FastMCP stdio server (used by CLI and bridge)."""
    logger.info("Starting SAT FastMCP Server (stdio)")
    await mcp.run_stdio_async()


if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(run_stdio_async())
