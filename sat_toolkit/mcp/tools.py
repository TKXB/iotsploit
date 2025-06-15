"""
MCP Tools for SAT Toolkit

Tools provide executable operations that LLMs can invoke.
These tools allow LLMs to interact with devices, execute exploits, and manage targets.
"""

import logging
from typing import Any, Dict, List, Optional
from mcp.types import Tool, TextContent
from .adapters import DeviceAdapter, TargetAdapter, ExploitAdapter, SecurityAdapter
from .security import SecurityManager

logger = logging.getLogger(__name__)

class ToolHandler:
    """Handles MCP tool execution for SAT Toolkit"""
    
    def __init__(self):
        self.device_adapter = DeviceAdapter()
        self.target_adapter = TargetAdapter()
        self.exploit_adapter = ExploitAdapter()
        self.security_adapter = SecurityAdapter()
        self.security_manager = SecurityManager()
    
    def get_available_tools(self) -> List[Tool]:
        """Get list of all available tools"""
        return [
            Tool(
                name="scan_wifi_networks",
                description="Scan for WiFi networks using connected ESP32 devices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Specific device ID to use (optional)"
                        }
                    }
                }
            ),
            Tool(
                name="execute_device_command",
                description="Execute a command on a connected device",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "driver_name": {
                            "type": "string",
                            "description": "Name of the device driver"
                        },
                        "command": {
                            "type": "string",
                            "description": "Command to execute"
                        },
                        "device_id": {
                            "type": "string",
                            "description": "Device ID (optional)"
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Command parameters (optional)"
                        }
                    },
                    "required": ["driver_name", "command"]
                }
            ),
            Tool(
                name="scan_devices",
                description="Scan for available devices using a specific driver",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "driver_name": {
                            "type": "string",
                            "description": "Name of the device driver to use for scanning"
                        }
                    },
                    "required": ["driver_name"]
                }
            ),
            Tool(
                name="execute_safe_exploit",
                description="Execute a safe exploit (security assessment) on a target",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "exploit_name": {
                            "type": "string",
                            "description": "Name of the exploit to execute"
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Exploit parameters (optional)"
                        }
                    },
                    "required": ["exploit_name"]
                }
            ),
            Tool(
                name="execute_dangerous_exploit",
                description="Execute a dangerous exploit (requires approval) on a target",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "exploit_name": {
                            "type": "string",
                            "description": "Name of the exploit to execute"
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Exploit parameters (optional)"
                        },
                        "confirmation": {
                            "type": "boolean",
                            "description": "Explicit confirmation for dangerous operation"
                        }
                    },
                    "required": ["exploit_name", "confirmation"]
                }
            ),
            Tool(
                name="flash_device_firmware",
                description="Flash firmware to a device (dangerous operation)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "driver_name": {
                            "type": "string",
                            "description": "Name of the device driver"
                        },
                        "device_id": {
                            "type": "string",
                            "description": "Device ID"
                        },
                        "firmware_name": {
                            "type": "string",
                            "description": "Name of the firmware to flash"
                        },
                        "confirmation": {
                            "type": "boolean",
                            "description": "Explicit confirmation for dangerous operation"
                        }
                    },
                    "required": ["driver_name", "device_id", "firmware_name", "confirmation"]
                }
            ),
            Tool(
                name="get_system_status",
                description="Get overall system status and health information",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="set_current_target",
                description="Set the current target for operations",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "ID of the target to set as current"
                        }
                    },
                    "required": ["target_id"]
                }
            )
        ]
    
    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a tool with given arguments"""
        try:
            if name == "scan_wifi_networks":
                return self._scan_wifi_networks(arguments)
            elif name == "execute_device_command":
                return self._execute_device_command(arguments)
            elif name == "scan_devices":
                return self._scan_devices(arguments)
            elif name == "execute_safe_exploit":
                return self._execute_safe_exploit(arguments)
            elif name == "execute_dangerous_exploit":
                return self._execute_dangerous_exploit(arguments)
            elif name == "flash_device_firmware":
                return self._flash_device_firmware(arguments)
            elif name == "get_system_status":
                return self._get_system_status(arguments)
            elif name == "set_current_target":
                return self._set_current_target(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return [TextContent(
                type="text",
                text=f"Error executing {name}: {str(e)}"
            )]
    
    def _scan_wifi_networks(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Scan for WiFi networks using ESP32 devices"""
        device_id = arguments.get("device_id")
        
        try:
            # Get available ESP32 devices
            devices = self.device_adapter.get_available_devices()
            esp32_devices = [d for d in devices if "esp32" in d.get("driver", "").lower()]
            
            if not esp32_devices:
                return [TextContent(
                    type="text",
                    text="No ESP32 devices available for WiFi scanning"
                )]
            
            # Use specific device if provided, otherwise use first available
            target_device = None
            if device_id:
                target_device = next((d for d in esp32_devices if d["device_id"] == device_id), None)
                if not target_device:
                    return [TextContent(
                        type="text",
                        text=f"ESP32 device {device_id} not found"
                    )]
            else:
                target_device = esp32_devices[0]
            
            # Execute WiFi scan
            result = self.device_adapter.execute_device_command(
                target_device["driver"],
                "scan_wifi",
                target_device["device_id"]
            )
            
            if result.get("status") == "success":
                networks = result.get("networks", [])
                response = f"WiFi scan completed on device {target_device['device_id']}:\n\n"
                response += f"Found {len(networks)} networks:\n"
                
                for network in networks:
                    response += f"- SSID: {network.get('ssid', 'Unknown')}\n"
                    response += f"  Signal: {network.get('rssi', 'Unknown')}\n"
                    response += f"  Channel: {network.get('channel', 'Unknown')}\n"
                    response += f"  Security: {network.get('security', 'Unknown')}\n\n"
                
                return [TextContent(type="text", text=response)]
            else:
                return [TextContent(
                    type="text",
                    text=f"WiFi scan failed: {result.get('message', 'Unknown error')}"
                )]
                
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error during WiFi scan: {str(e)}"
            )]
    
    def _execute_device_command(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a command on a device"""
        driver_name = arguments["driver_name"]
        command = arguments["command"]
        device_id = arguments.get("device_id", "")
        parameters = arguments.get("parameters", {})
        
        # Check if operation is safe
        risk_level = self.security_adapter.classify_operation_risk(command, parameters)
        
        if not self.security_manager.is_operation_allowed(command, risk_level):
            return [TextContent(
                type="text",
                text=f"Operation '{command}' is classified as {risk_level} and requires explicit approval"
            )]
        
        try:
            result = self.device_adapter.execute_device_command(
                driver_name, command, device_id, **parameters
            )
            
            response = f"Command '{command}' executed on {driver_name}"
            if device_id:
                response += f" (device: {device_id})"
            response += f"\n\nResult: {self._format_result(result)}"
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error executing command '{command}' on {driver_name}: {str(e)}"
            )]
    
    def _scan_devices(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Scan for devices using a specific driver or all available drivers"""
        driver_name = arguments.get("driver_name", "")
        
        try:
            # If no driver specified or driver doesn't exist, scan all enabled drivers
            from sat_toolkit.core.device_manager import DeviceDriverManager
            device_manager = DeviceDriverManager()
            available_drivers = device_manager.list_drivers()
            enabled_drivers = [d for d in available_drivers if device_manager.is_driver_enabled(d)]
            
            if not driver_name or driver_name not in available_drivers:
                # Scan all enabled drivers
                response = "Device scan completed for all enabled drivers:\n\n"
                total_devices = 0
                
                for driver in enabled_drivers:
                    try:
                        result = self.device_adapter.scan_devices(driver)
                        if result.get("status") == "success":
                            devices = result.get("devices", [])
                            response += f"Driver '{driver}': Found {len(devices)} devices\n"
                            
                            for device in devices:
                                response += f"  - Device ID: {device.device_id}\n"
                                response += f"    Name: {device.name}\n"
                                response += f"    Type: {device.device_type}\n"
                                if hasattr(device, 'attributes') and device.attributes:
                                    # Show key attributes only
                                    key_attrs = {k: v for k, v in device.attributes.items() 
                                               if k in ['port', 'serial_number', 'vendor_id', 'product_id']}
                                    if key_attrs:
                                        response += f"    Key Attributes: {key_attrs}\n"
                                response += "\n"
                            total_devices += len(devices)
                        else:
                            response += f"Driver '{driver}': {result.get('message', 'Scan failed')}\n"
                    except Exception as e:
                        response += f"Driver '{driver}': Error - {str(e)}\n"
                
                response += f"\nTotal devices found: {total_devices}\n"
                response += f"Enabled drivers: {len(enabled_drivers)} ({', '.join(enabled_drivers)})\n"
                
                if not enabled_drivers:
                    response += "\nNo enabled drivers found. Use 'enable_driver' command to enable drivers.\n"
                
                return [TextContent(type="text", text=response)]
            
            else:
                # Scan specific driver
                result = self.device_adapter.scan_devices(driver_name)
                
                if result.get("status") == "success":
                    devices = result.get("devices", [])
                    response = f"Device scan completed for driver '{driver_name}':\n\n"
                    response += f"Found {len(devices)} devices:\n"
                    
                    for device in devices:
                        response += f"- Device ID: {device.device_id}\n"
                        response += f"  Name: {device.name}\n"
                        response += f"  Type: {device.device_type}\n"
                        if hasattr(device, 'attributes') and device.attributes:
                            response += f"  Attributes: {device.attributes}\n"
                        response += "\n"
                    
                    return [TextContent(type="text", text=response)]
                else:
                    return [TextContent(
                        type="text",
                        text=f"Device scan failed for '{driver_name}': {result.get('message', 'Unknown error')}"
                    )]
                
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error scanning devices: {str(e)}"
            )]
    
    def _execute_safe_exploit(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a safe exploit"""
        exploit_name = arguments["exploit_name"]
        parameters = arguments.get("parameters", {})
        
        # Verify exploit is actually safe
        exploit_info = self.exploit_adapter.get_exploit_info(exploit_name)
        if not exploit_info:
            return [TextContent(
                type="text",
                text=f"Exploit '{exploit_name}' not found"
            )]
        
        if exploit_info.get("requires_root", False):
            return [TextContent(
                type="text",
                text=f"Exploit '{exploit_name}' is classified as dangerous and requires explicit approval"
            )]
        
        try:
            current_target = self.target_adapter.get_current_target()
            result = self.exploit_adapter.execute_exploit(exploit_name, current_target, parameters)
            
            response = f"Safe exploit '{exploit_name}' executed:\n\n"
            response += f"Status: {result.get('status', 'Unknown')}\n"
            response += f"Message: {result.get('message', 'No message')}\n"
            
            if result.get("data"):
                response += f"\nResults:\n{self._format_result(result['data'])}"
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error executing exploit '{exploit_name}': {str(e)}"
            )]
    
    def _execute_dangerous_exploit(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a dangerous exploit with confirmation"""
        exploit_name = arguments["exploit_name"]
        parameters = arguments.get("parameters", {})
        confirmation = arguments.get("confirmation", False)
        
        if not confirmation:
            return [TextContent(
                type="text",
                text=f"Dangerous exploit '{exploit_name}' requires explicit confirmation. Set 'confirmation': true to proceed."
            )]
        
        try:
            current_target = self.target_adapter.get_current_target()
            if not current_target:
                return [TextContent(
                    type="text",
                    text="No target selected. Please set a target before executing exploits."
                )]
            
            result = self.exploit_adapter.execute_exploit(exploit_name, current_target, parameters)
            
            response = f"Dangerous exploit '{exploit_name}' executed with confirmation:\n\n"
            response += f"Target: {current_target.get('name', 'Unknown')}\n"
            response += f"Status: {result.get('status', 'Unknown')}\n"
            response += f"Message: {result.get('message', 'No message')}\n"
            
            if result.get("data"):
                response += f"\nResults:\n{self._format_result(result['data'])}"
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error executing dangerous exploit '{exploit_name}': {str(e)}"
            )]
    
    def _flash_device_firmware(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Flash firmware to a device (dangerous operation)"""
        driver_name = arguments["driver_name"]
        device_id = arguments["device_id"]
        firmware_name = arguments["firmware_name"]
        confirmation = arguments.get("confirmation", False)
        
        if not confirmation:
            return [TextContent(
                type="text",
                text="Firmware flashing is a dangerous operation that requires explicit confirmation. Set 'confirmation': true to proceed."
            )]
        
        try:
            result = self.device_adapter.execute_device_command(
                driver_name,
                "flash_firmware",
                device_id,
                firmware_name=firmware_name
            )
            
            response = f"Firmware flashing completed on {driver_name} device {device_id}:\n\n"
            response += f"Firmware: {firmware_name}\n"
            response += f"Result: {self._format_result(result)}"
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error flashing firmware on {driver_name} device {device_id}: {str(e)}"
            )]
    
    def _get_system_status(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Get overall system status"""
        try:
            status = self.security_adapter.get_security_status()
            devices = self.device_adapter.get_available_devices()
            current_target = self.target_adapter.get_current_target()
            
            response = "SAT Toolkit System Status:\n\n"
            response += f"Current Target: {current_target.get('name') if current_target else 'None'}\n"
            response += f"Connected Devices: {len(devices)}\n"
            response += f"Available Exploits: {status.get('available_exploits', 0)}\n"
            response += f"Safe Exploits: {status.get('safe_exploits', 0)}\n"
            response += f"Dangerous Exploits: {status.get('dangerous_exploits', 0)}\n"
            response += f"Active Drivers: {status.get('active_drivers', 0)}\n\n"
            
            if devices:
                response += "Connected Devices:\n"
                for device in devices[:5]:  # Show first 5 devices
                    response += f"- {device.get('name', 'Unknown')} ({device.get('driver', 'Unknown')})\n"
                if len(devices) > 5:
                    response += f"... and {len(devices) - 5} more devices\n"
            
            return [TextContent(type="text", text=response)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error getting system status: {str(e)}"
            )]
    
    def _set_current_target(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Set the current target"""
        target_id = arguments["target_id"]
        
        try:
            # This would need to be implemented in the target adapter
            # For now, return a message indicating the limitation
            return [TextContent(
                type="text",
                text=f"Target setting functionality needs to be implemented. Target ID: {target_id}"
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error setting current target: {str(e)}"
            )]
    
    def _format_result(self, result: Any) -> str:
        """Format result for display"""
        if isinstance(result, dict):
            import json
            return json.dumps(result, indent=2, default=str)
        elif isinstance(result, list):
            import json
            return json.dumps(result, indent=2, default=str)
        else:
            return str(result) 