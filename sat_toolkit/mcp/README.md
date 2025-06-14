# SAT Toolkit MCP Integration

This directory contains the Model Context Protocol (MCP) integration for the SAT Toolkit, enabling AI/LLM applications to interact with embedded devices, execute security exploits, and manage penetration testing operations.

## Overview

The MCP integration provides a standardized interface for AI applications to:

- **Device Management**: Scan, connect, and control embedded devices (ESP32, FPGA, etc.)
- **Security Assessment**: Execute safe security checks and vulnerability assessments
- **Exploit Execution**: Run penetration testing tools with proper safety controls
- **Target Management**: Manage and interact with target systems
- **Real-time Monitoring**: Access device status, WiFi networks, and system health

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AI/LLM App    │    │   MCP Server    │    │  SAT Toolkit    │
│                 │◄──►│                 │◄──►│                 │
│ - Claude        │    │ - Resources     │    │ - Device Mgr    │
│ - ChatGPT       │    │ - Tools         │    │ - Exploit Mgr   │
│ - Custom Apps   │    │ - Security      │    │ - Target Mgr    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Components

### 1. MCP Server (`server.py`)
Main MCP protocol implementation that handles:
- Resource listing and reading
- Tool execution with security controls
- Protocol compliance and error handling

### 2. Resources (`resources.py`)
Read-only context providers:
- `sat://devices/list` - Available devices and their status
- `sat://devices/capabilities` - Device driver capabilities
- `sat://targets/current` - Current target information
- `sat://targets/list` - All available targets
- `sat://exploits/catalog` - Available exploit plugins
- `sat://security/status` - Overall security status
- `sat://wifi/networks` - WiFi scan results

### 3. Tools (`tools.py`)
Executable operations:
- `scan_wifi_networks` - WiFi scanning using ESP32 devices
- `execute_device_command` - Execute commands on devices
- `scan_devices` - Scan for available devices
- `execute_safe_exploit` - Run safe security assessments
- `execute_dangerous_exploit` - Run dangerous exploits (with confirmation)
- `flash_device_firmware` - Flash firmware to devices (dangerous)
- `get_system_status` - Get overall system status

### 4. Adapters (`adapters.py`)
Bridge between MCP and SAT Toolkit:
- `DeviceAdapter` - Interfaces with DeviceDriverManager
- `TargetAdapter` - Interfaces with TargetManager
- `ExploitAdapter` - Interfaces with ExploitPluginManager
- `SecurityAdapter` - Security status and risk assessment

### 5. Security (`security.py`)
Security controls and risk management:
- Operation classification (safe/dangerous)
- Permission checking
- Confirmation requirements for dangerous operations

## Installation

1. Install MCP Python SDK:
```bash
pip install mcp
```

2. Ensure SAT Toolkit dependencies are installed:
```bash
pip install -r requirements.txt
```

## Usage

### Running the MCP Server

```bash
# Run the server
python -m sat_toolkit.mcp.cli run

# Test components
python -m sat_toolkit.mcp.cli test-all

# Test specific components
python -m sat_toolkit.mcp.cli test-resources
python -m sat_toolkit.mcp.cli test-tools
python -m sat_toolkit.mcp.cli test-adapters
```

### Connecting from AI Applications

#### Claude Desktop Configuration
Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "sat-toolkit": {
      "command": "python",
      "args": ["-m", "sat_toolkit.mcp.cli", "run"],
      "cwd": "/path/to/sat_toolkit"
    }
  }
}
```

#### Custom Applications
```python
from mcp.client import ClientSession
from mcp.client.stdio import stdio_client

async def connect_to_sat_toolkit():
    async with stdio_client(["python", "-m", "sat_toolkit.mcp.cli", "run"]) as client:
        # List available resources
        resources = await client.list_resources()
        
        # Read device information
        devices = await client.read_resource("sat://devices/list")
        
        # Execute WiFi scan
        result = await client.call_tool("scan_wifi_networks", {})
```

## Security Model

The MCP integration implements a multi-layered security model:

### Operation Classification
- **Safe**: Read-only operations, basic device queries, safe security assessments
- **Medium**: Network scanning, non-destructive testing
- **Dangerous**: Firmware flashing, root exploits, system modifications

### Permission Controls
- Safe operations: Allowed by default
- Medium operations: Require explicit parameters
- Dangerous operations: Require explicit confirmation (`"confirmation": true`)

### Examples

```python
# Safe operation - no confirmation needed
await client.call_tool("scan_wifi_networks", {})

# Dangerous operation - requires confirmation
await client.call_tool("flash_device_firmware", {
    "driver_name": "drv_esp32",
    "device_id": "esp32s3_001", 
    "firmware_name": "wifi_penetration_tool",
    "confirmation": true  # Required!
})
```

## Available Resources

### Device Information
```python
# Get all devices
devices = await client.read_resource("sat://devices/list")

# Get device capabilities
capabilities = await client.read_resource("sat://devices/capabilities")
```

### Target Information
```python
# Get current target
target = await client.read_resource("sat://targets/current")

# Get all targets
targets = await client.read_resource("sat://targets/list")
```

### Security Status
```python
# Get security overview
status = await client.read_resource("sat://security/status")

# Get exploit catalog
exploits = await client.read_resource("sat://exploits/catalog")
```

## Available Tools

### Device Operations
```python
# Scan for WiFi networks
result = await client.call_tool("scan_wifi_networks", {
    "device_id": "esp32s3_001"  # Optional
})

# Execute device command
result = await client.call_tool("execute_device_command", {
    "driver_name": "drv_esp32",
    "command": "get_status",
    "device_id": "esp32s3_001",
    "parameters": {}
})

# Scan for devices
result = await client.call_tool("scan_devices", {
    "driver_name": "drv_esp32"
})
```

### Security Operations
```python
# Run safe security check
result = await client.call_tool("execute_safe_exploit", {
    "exploit_name": "adb_check",
    "parameters": {
        "device_serial": "2fd1f89",
        "try_root": false
    }
})

# Run dangerous exploit (requires confirmation)
result = await client.call_tool("execute_dangerous_exploit", {
    "exploit_name": "hydra_ssh_attack",
    "parameters": {
        "username": "root",
        "password_list": "weak_passwords.txt"
    },
    "confirmation": true
})
```

### System Management
```python
# Get system status
status = await client.call_tool("get_system_status", {})

# Set current target
result = await client.call_tool("set_current_target", {
    "target_id": "android_device_001"
})
```

## Error Handling

The MCP server provides comprehensive error handling:

```python
try:
    result = await client.call_tool("scan_wifi_networks", {})
except Exception as e:
    print(f"Tool execution failed: {e}")
```

Common error scenarios:
- Device not connected
- Driver not enabled
- Insufficient permissions
- Missing confirmation for dangerous operations
- Target not selected

## Logging

The server provides detailed logging:

```bash
# Enable debug logging
python -m sat_toolkit.mcp.cli run --log-level DEBUG

# Logs are written to sat_mcp_server.log
tail -f sat_mcp_server.log
```

## Integration Examples

### AI-Powered Penetration Testing
```python
# AI can now:
# 1. Scan for devices
devices = await client.read_resource("sat://devices/list")

# 2. Scan WiFi networks
wifi_result = await client.call_tool("scan_wifi_networks", {})

# 3. Run security assessments
security_result = await client.call_tool("execute_safe_exploit", {
    "exploit_name": "adb_check"
})

# 4. Make intelligent decisions based on results
if security_result["success"]:
    # Proceed with more advanced testing
    pass
```

### Automated Device Management
```python
# AI can manage device lifecycle:
# 1. Scan for new devices
scan_result = await client.call_tool("scan_devices", {
    "driver_name": "drv_esp32"
})

# 2. Flash firmware if needed
if needs_firmware_update:
    flash_result = await client.call_tool("flash_device_firmware", {
        "driver_name": "drv_esp32",
        "device_id": device_id,
        "firmware_name": "latest_firmware",
        "confirmation": true
    })
```

## Development

### Adding New Resources
1. Add resource definition to `ResourceProvider.get_available_resources()`
2. Implement content provider method
3. Add URI handling in `get_resource_content()`

### Adding New Tools
1. Add tool definition to `ToolHandler.get_available_tools()`
2. Implement tool execution method
3. Add tool handling in `execute_tool()`
4. Consider security implications

### Testing
```bash
# Test all components
python -m sat_toolkit.mcp.cli test-all

# Test specific functionality
python -m sat_toolkit.mcp.cli test-resources
python -m sat_toolkit.mcp.cli test-tools
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure SAT Toolkit is in Python path
2. **Device Not Found**: Check device connections and driver status
3. **Permission Denied**: Verify dangerous operations have confirmation
4. **Target Not Set**: Set current target before running exploits

### Debug Mode
```bash
python -m sat_toolkit.mcp.cli run --log-level DEBUG
```

## Contributing

1. Follow existing code patterns
2. Add comprehensive error handling
3. Include security considerations
4. Update documentation
5. Add tests for new functionality

## License

This MCP integration follows the same license as the SAT Toolkit project. 