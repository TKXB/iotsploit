# iotsploit-platforms

IoTSploit platform-specific adapters package.

This package provides platform-specific implementations for WiFi, Input, and SSH backends across different operating systems.

## Structure

```
iotsploit-platforms/
├── src/
│   └── iotsploit_platforms/
│       ├── adapters/
│       │   └── platforms/
│       │       ├── linux/
│       │       │   └── wifi_backend.py
│       │       ├── windows/
│       │       │   └── wifi_backend.py
│       │       └── darwin/
│       │           └── wifi_backend.py
│       └── platforms/
│           └── __init__.py  # Platform distribution module
└── pyproject.toml
```

## Usage

The platform distribution module automatically selects the appropriate backend based on the current platform:

```python
from iotsploit_platforms.platforms import wifi_backend

# wifi_backend is the appropriate backend class for the current platform
backend = wifi_backend(wifi_iface_name="wlan0")
networks = backend.scan()
```

## Platform Support

- **Linux**: Full WiFi backend implementation using NetworkManager (libnm via GObject Introspection, with DBus for hotspot/AP mode)
- **Windows**: Placeholder implementation (not yet implemented)
- **Darwin (macOS)**: Placeholder implementation (not yet implemented)

## Dependencies

- `iotsploit-core`: Core interfaces and utilities
- NetworkManager + `python3-gi` (libnm) and `dbus-python`: WiFi operations on Linux
