# IoTSploit

**The Swiss Army Knife in the field of IoT security testing**

IoTSploit is a comprehensive cybersecurity testing framework that modularizes testing scripts and hardware, enabling security assessments of various IoT devices. It provides a complete suite of tools and features to identify vulnerabilities and ensure the robustness of IoT systems against potential threats.

## 📋 About This Repository

This repository contains the **core Python server-side code** of IoTSploit, which includes:
- The main testing framework and plugin system
- All security testing plugins and exploits
- Device drivers and protocol implementations
- Command-line interface (CLI) shell
- Web API and backend services

**Two ways to use IoTSploit:**

1. **Command-Line Interface** (included in this repo): Use the built-in Python shell for direct interaction with the framework
2. **Graphical User Interface** (separate download): Download the Flutter desktop/mobile apps that connect to this Python backend

The GUI applications provide a user-friendly interface but require this Python core to be running as the backend server.

## 🚀 Features

### 🔍 Vulnerability Detection
Built-in tools to identify common IoT device vulnerabilities across multiple protocols and interfaces.

### 🧠 Smart & Intuitive
User-friendly interface for effortless security testing with both command-line and graphical interfaces.

### 🔧 Modular Design
Flexibly integrate and swap out testing scripts and hardware modules to adapt to different testing scenarios.

### 🌐 Multi-Transport Support
Supports a variety of IoT protocols including:
- UART
- JTAG
- BLE (Bluetooth Low Energy)
- CAN Bus
- SPI
- I2C
- USB
- WiFi

### 🤖 Automation Features
Enables automated and repeatable testing processes with plugin-based architecture.

### 📱 Cross-Platform
- **Command Line Interface**: Cmd2-powered REPL shell for power users
- **Flutter Desktop App**: Beautiful graphical interface available for Windows, macOS, and Linux
- **Mobile Apps**: iOS & Android apps available for remote control and monitoring

## 📥 Downloads

### Desktop Applications
The IoTSploit Flutter desktop application is available for download from the official website:

- **Windows**: Compatible with Windows 10/11 (64-bit) - MSI Installer & Portable Version
- **macOS**: Compatible with macOS 10.15+ (Intel & Apple Silicon) - Universal Binary DMG Package  
- **Linux**: Compatible with Ubuntu 20.04+, Debian 11+, CentOS 8+ - DEB, RPM, AppImage, and Snap packages

### Mobile Applications
Control IoTSploit remotely from your mobile device:

- **iOS App**: Available on the App Store (iOS 13.0 or later)
- **Android App**: Available on Google Play (Android 7.0 or later)

### Hardware & Firmware
- **Firmware**: Latest firmware for IoTSploit hardware modules
- **Drivers**: USB and hardware drivers for all supported platforms
- **Schematics**: Hardware documentation and schematics

**Download all applications and resources**: [https://www.iotsploit.org/download.html](https://www.iotsploit.org/download.html)

## 🏗️ Architecture

### Plugin System
IoTSploit features a powerful plugin system built on Python that lets you extend the platform with custom security testing modules:

- **Modular design** with pluggable interfaces
- **Extensive library** of security testing plugins
- **Custom plugin development** with Python API
- **Real-time results** with execution status tracking
- **Automatic UI generation** from Python plugin definitions

### Hardware Modularity
Leveraging the versatile M.2 Key E slot, IoTSploit enables seamless integration of diverse hardware modules:

- **IoTSploit Motherboard**: 100M Ethernet Switch, USB 2.0 HUB, 3 M.2 Key E Slots
- **LPC4330 Board**: USB simulation capabilities, Bad USB attacks
- **ESP32 Board**: WiFi and Bluetooth-based security assessments
- **FPGA Board**: 16-channel logic analyzer with protocol decoding

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8+
- Docker (for Redis)
- Git

### 1. Clone the Repository and Switch to Development Branch

```bash
git clone https://github.com/iotsploit/iotsploit.git
cd iotsploit
git fetch
git checkout -b dev origin/dev
```

### 2. Set Up Redis

Ensure you have Docker installed, then run:

```bash
docker pull redis
docker run --name sat-redis -p 6379:6379 -d redis:latest
```

### 3. Install and Configure Poetry

Poetry is used for dependency management:

```bash
pip install poetry
pip install poetry-plugin-shell
poetry lock        # This may take 10-20 minutes
poetry install     # This may take 10-20 minutes
poetry shell
```

### 4. Initialize the Django Database

Set up the database:

```bash
python manage.py makemigrations
python manage.py makemigrations sat_toolkit
python manage.py migrate
```

### 5. Start the Application

Launch the application:

```bash
python console.py
```

## 📖 Usage

### IoTSploit Shell Commands

Once the application is running, you can interact with it using the IoTSploit Shell:

#### System Commands
- **exploit**: Execute all plugins in the IoTSploit System
- **exit**: Exit the IoTSploit Shell

#### Device Commands
- **device_info**: Show Device Info
- **list_devices**: List all devices stored in the database
- **list_device_drivers**: List all available device plugins

#### Network Commands
- **connect_lab_wifi**: Connect to Lab WiFi

#### Django Commands
- **runserver**: Start Django development server, Daphne WebSocket server, and Celery worker
- **stop_server**: Stop all servers and workers

#### Plugin Commands
- **list_plugins**: List all available plugins
- **execute_plugin**: Execute a specific plugin
- **flash_plugins**: Refresh and reload all plugins
- **create_group**: Create a plugin group
- **execute_group**: Execute plugins in a group
- **list_groups**: List all available plugin groups

#### Target Commands
- **list_targets**: List all targets stored in the database
- **target_select**: Select a target from available targets
- **edit_target**: Edit an existing target

#### Test Commands
- **test_select**: Select Test Project
- **run_test**: Start Test Project
- **quick_test**: Run Test Project quickly

#### Utility Commands
- **help**: List available commands or get detailed help
- **set_log_level**: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **ls**: List directory contents
- **lsusb**: List USB devices

### Example Plugin Usage

```python
class AdbSecurityCheckPlugin(BasePlugin):
    def __init__(self):
        super().__init__({
            'Name': 'Android ADB Security Audit',
            'Description': 'Performs security checks on an Android device',
            'License': 'GPL',
            'Author': ['iotsploit'],
            'Parameters': {
                'device_serial': {
                    'type': 'string',
                    'required': False,
                    'description': 'ADB device serial number',
                    'default': '2fd1f89'
                },
                'try_root': {
                    'type': 'bool',
                    'required': False,
                    'description': 'Attempt to gain root access',
                    'default': False
                }
            }
        })

    @hookimpl
    def execute(self, target=None, parameters=None) -> ExploitResult:
        # Your plugin logic here
        return ExploitResult(True, "Test completed", {"status": "success"})
```

## 📄 License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0).

The GPL-3.0 license ensures that:
- You can freely use, modify, and distribute this software
- Any derivative works must also be licensed under GPL-3.0
- Source code must be made available when distributing the software
- Commercial use is permitted under the terms of the license

For the full license text, see the [LICENSE](LICENSE) file in this repository.

## 🤝 How to Contribute

We welcome contributions from the community! Here's how you can help improve IoTSploit:

### 🐛 Reporting Issues

1. **Search existing issues** first to avoid duplicates
2. **Use the issue templates** when creating new issues
3. **Provide detailed information** including:
   - Steps to reproduce the issue
   - Expected vs actual behavior
   - System information (OS, Python version, etc.)
   - Relevant logs or error messages

### 💻 Contributing Code

1. **Fork the repository** and create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Follow the coding standards**:
   - Use Python PEP 8 style guidelines
   - Add docstrings to functions and classes
   - Include type hints where appropriate
   - Write unit tests for new functionality

3. **Test your changes**:
   ```bash
   # Run existing tests
   python -m pytest
   
   # Test your plugin
   python console.py
   ```

4. **Submit a Pull Request**:
   - Provide a clear description of your changes
   - Reference any related issues
   - Ensure all tests pass
   - Update documentation if necessary

### 🔌 Creating Plugins

1. **Plugin Structure**: Follow the existing plugin structure in `plugins/exploits/`
2. **Base Class**: Inherit from `BasePlugin` and implement required methods
3. **Documentation**: Include clear parameter descriptions and usage examples
4. **Testing**: Test your plugin thoroughly with different target configurations

### 📚 Documentation

- **Wiki contributions**: Help improve our [documentation](https://www.iotsploit.org/)
- **Code comments**: Add clear comments to complex code sections
- **Examples**: Provide usage examples and tutorials

### 💬 Community

- **GitHub Discussions**: Participate in community discussions
- **Code Review**: Help review pull requests from other contributors
- **Feature Requests**: Suggest new features and improvements

### 📋 Development Guidelines

1. **Code Quality**: Maintain high code quality with proper error handling
2. **Security**: Follow security best practices, especially for exploit code
3. **Compatibility**: Ensure compatibility across different platforms
4. **Performance**: Consider performance implications of your changes

For more detailed contribution guidelines, please see [CONTRIBUTING.md](CONTRIBUTING.md).

## 🌟 Community & Support

- **Website**: [https://www.iotsploit.org/](https://www.iotsploit.org/)
- **Documentation**: [IoTSploit Wiki](https://www.iotsploit.org/)
- **GitHub**: [IoTSploit Repository](https://github.com/iotsploit/iotsploit)
- **Issues**: [Report bugs and request features](https://github.com/iotsploit/iotsploit/issues)

## 🙏 Acknowledgments

IoTSploit is developed and maintained by the IoTSploit community. We thank all contributors who help make this project better.

---

**⚠️ Disclaimer**: IoTSploit is intended for authorized security testing and educational purposes only. Users are responsible for complying with applicable laws and regulations. The developers assume no liability for misuse of this software.
