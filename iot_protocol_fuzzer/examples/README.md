# IoT Protocol Fuzzer Examples

This directory contains example scripts demonstrating how to use the IoT Protocol Fuzzer for different communication protocols.

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install python-can pyserial spidev  # Install based on your needs
   ```

2. **Install Radamsa:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install radamsa
   
   # Or compile from source
   git clone https://gitlab.com/akihe/radamsa.git
   cd radamsa
   make
   sudo make install
   ```
   
   **Custom Radamsa Path Configuration:**
   If you have radamsa in a custom location (like `/home/tkxb/Projects/radamsa/bin/radamsa`), you have several options:
   
   ```bash
   # Option 1: Use the configuration helper (recommended)
   python configure_radamsa.py
   # Or specify custom path directly
   python configure_radamsa.py /home/tkxb/Projects/radamsa/bin/radamsa
   
   # Option 2: Add to PATH manually
   export PATH="/home/tkxb/Projects/radamsa/bin:$PATH"
   echo 'export PATH="/home/tkxb/Projects/radamsa/bin:$PATH"' >> ~/.bashrc
   
   # Option 3: Create symlink
   sudo ln -s /home/tkxb/Projects/radamsa/bin/radamsa /usr/local/bin/radamsa
   
   # Option 4: Update examples manually to use absolute path (already done in examples)
   ```

3. **Hardware setup:**
   - Connect your target device via appropriate interface
   - Ensure proper permissions for device access
   - Configure device settings (baud rate, device path, etc.)

## Quick Start

### 0. Configure Radamsa Path (`configure_radamsa.py`)

**Purpose:** Automatically find and configure radamsa path for all examples

**Usage:**
```bash
# Auto-detect radamsa location
python configure_radamsa.py

# Or specify custom path
python configure_radamsa.py /home/tkxb/Projects/radamsa/bin/radamsa
```

**What it does:**
- Searches for radamsa on your system
- Tests radamsa functionality
- Updates all example files with correct path
- Shows ready-to-run instructions

### 1. Test Your Setup (`test_setup.py`)

**Purpose:** Verify all dependencies and configurations are working

**Usage:**
```bash
python test_setup.py
```

**What it tests:**
- Radamsa binary functionality
- RadamsaGenerator import and mutation
- All harnesses (CAN, UART, SPI)
- Interface dependencies
- Orchestrator functionality
- Example file configuration

## Examples

### 2. Simple CAN Fuzzing (`simple_can_fuzz.py`)

**Purpose:** Basic CAN bus fuzzing with minimal configuration

**Requirements:**
- CAN interface (e.g., USB-CAN adapter)
- `can-utils` package
- SocketCAN configured

**Setup:**
```bash
# Configure CAN interface
sudo modprobe can
sudo modprobe can_raw
sudo ip link set can0 type can bitrate 500000
sudo ip link set up can0

# Verify interface
ip link show can0
```

**Usage:**
```bash
python simple_can_fuzz.py
```

**What it does:**
- Uses single seed: `\x00\x01\x02\x03`
- Runs 100 iterations
- Sends 8-byte CAN frames with ID 0x123
- Logs results and crashes

### 3. Simple UART Fuzzing (`simple_uart_fuzz.py`)

**Purpose:** Basic UART/serial fuzzing with common command patterns

**Requirements:**
- USB-to-serial adapter or device with UART interface
- Target device connected to `/dev/ttyUSB0`

**Setup:**
```bash
# Check device
ls -la /dev/ttyUSB*

# Set permissions (if needed)
sudo chmod 666 /dev/ttyUSB0
# Or add user to dialout group
sudo usermod -a -G dialout $USER
```

**Usage:**
```bash
python simple_uart_fuzz.py
```

**What it does:**
- Uses 8 seed patterns (AT commands, binary data, etc.)
- Runs 200 iterations
- Uses 115200 baud rate
- Includes error handling and troubleshooting

### 4. Advanced UART Fuzzing (`advanced_uart_fuzz.py`)

**Purpose:** Comprehensive UART fuzzing with multiple seed corpus types

**Features:**
- Multiple seed corpus types:
  - AT commands (for cellular/modem devices)
  - Protocol commands (HTTP-like, IoT protocols)
  - Malformed data (buffer overflows, injection attempts)
- Pre-flight connectivity checks
- Detailed logging to file
- Better error handling and cleanup

**Usage:**
```bash
python advanced_uart_fuzz.py
```

**Configuration:**
Edit the `seed_type` variable in `main()`:
- `"at_commands"` - AT command corpus
- `"protocols"` - Protocol command corpus  
- `"malformed"` - Malformed/edge case corpus
- `"all"` - Combined corpus

**Customization:**
```python
# Change device settings
uart_interface = UARTInterface(
    device="/dev/ttyUSB1",     # Your device path
    baudrate=9600,             # Match your device
    timeout=1.0                # Adjust for slow devices
)

# Modify campaign settings
config = CampaignConfig(
    iterations=1000,           # More/fewer iterations
    delay=0.1,                 # Slower/faster testing
    save_crashes=True          # Save crash artifacts
)
```

## Common Issues and Solutions

### Permission Errors
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER
# Then log out and back in

# Or temporary fix
sudo chmod 666 /dev/ttyUSB0
```

### Device Not Found
```bash
# List available devices
ls -la /dev/tty*
dmesg | grep tty

# Check if device is detected
lsusb
```

### CAN Interface Issues
```bash
# Check CAN interface status
ip link show can0

# Restart CAN interface
sudo ip link set can0 down
sudo ip link set can0 up
```

### Radamsa Not Found
```bash
# Check if radamsa is in PATH
which radamsa

# Install radamsa system-wide
sudo apt-get install radamsa

# Or add custom radamsa to PATH
export PATH="/home/tkxb/Projects/radamsa/bin:$PATH"

# Test radamsa is working
radamsa --version
# Or if using custom path
/home/tkxb/Projects/radamsa/bin/radamsa --version
```

## Output Files

The fuzzer creates several output files:

- **`artifacts/`** - Directory containing test results
  - `case_X.bin` - Individual test cases
  - `crash_X.bin` - Test cases that caused crashes
- **`uart_fuzz.log`** - Detailed log file (advanced example)

## Creating Custom Examples

To create your own fuzzing example:

1. **Choose your protocol harness:**
   ```python
   from iot_protocol_fuzzer.harnesses.can_harness import CANHarness
   from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
   from iot_protocol_fuzzer.harnesses.spi_harness import SPIHarness
   ```

2. **Create appropriate seed corpus:**
   ```python
   seeds = [
       b"your_protocol_command_1",
       b"your_protocol_command_2",
       # Add more seeds relevant to your target
   ]
   ```

3. **Configure the interface:**
   ```python
   # For UART
   uart_interface = UARTInterface(device="/dev/ttyUSB0", baudrate=115200)
   harness = UARTHarness(interface=uart_interface)
   
   # For CAN
   harness = CANHarness()  # Uses default SocketCAN settings
   ```

4. **Customize campaign settings:**
   ```python
   config = CampaignConfig(
       iterations=500,
       delay=0.05,
       save_crashes=True
   )
   ```

## Best Practices

1. **Start with simple examples** before moving to advanced ones
2. **Test connectivity** before running fuzzing campaigns
3. **Use appropriate seed corpus** for your target protocol
4. **Monitor target device** for signs of stress or failure
5. **Save important test cases** for regression testing
6. **Log everything** for later analysis

## Safety Considerations

- **Always test on dedicated hardware** - Don't fuzz production systems
- **Monitor power consumption** - Fuzzing can stress devices
- **Have recovery procedures** - Know how to reset/recover your target
- **Start with short campaigns** - Gradually increase iterations
- **Backup important data** before fuzzing

## Troubleshooting

For common issues and solutions, check:
1. Device connectivity and permissions
2. Interface configuration (baud rate, device path)
3. Radamsa installation and PATH
4. Target device responsiveness
5. Log files for detailed error information 