# iotsploit-drivers

Official IoTSploit device driver package. Contains all built-in hardware drivers.

## Included Drivers

| Driver | Module | Description |
|--------|--------|-------------|
| ESP32 | `iotsploit_drivers.esp32` | ESP32 device driver via SCPI |
| SocketCAN | `iotsploit_drivers.socketcan` | CAN bus driver via python-can |
| FT2232 | `iotsploit_drivers.ft2232` | FTDI FT2232 USB driver |
| GreatFET | `iotsploit_drivers.greatfet` | GreatFET One USB driver |
| Logic Analyzer | `iotsploit_drivers.logic` | Enxor logic analyzer driver |
| J-Link | `iotsploit_drivers.jlink` | SEGGER J-Link debug probe |
| Ubertooth | `iotsploit_drivers.ubertooth` | Ubertooth Bluetooth driver |
| FPGA | `iotsploit_drivers.iotsploit_func_fpga` | ECP5 FPGA driver |
| Ethernet VLAN | `iotsploit_drivers.ethernet` | Persistent NetworkManager VLAN configuration |

### Ethernet VLAN

`drv_eth_vlan` scans NetworkManager Ethernet parents and exposes `add_vlan`,
`edit_vlan`, `delete_vlan`, and the read-only `vlan_status` command. Profiles
created by the driver are named `iotsploit-vlan-<parent>-<id>`; edit and delete
refuse every other profile. The VLAN address, cloned MAC, and autoconnect state
persist in NetworkManager. An optional permanent peer neighbor is applied to
the live interface during add or edit, but must be reapplied after reboot.

## Installation

```bash
pip install iotsploit-drivers
```

For development:

```bash
pip install -e ./iotsploit-drivers
```
