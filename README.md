# IoTSploit

**IoT security testing from a single framework**

IoTSploit modularizes security-testing scripts and hardware so you can assess all
kinds of IoT devices. It combines an interactive shell, a plugin and exploit
system, device drivers, protocol clients, a fuzzer, and GUI backends — distributed
as several installable packages.

**Two ways to use IoTSploit:**

1. **Command-Line Interface**: Install `iotsploit-cli` from PyPI and run the interactive `iotsploit` shell
2. **Graphical User Interface** (separate download): Download the Flutter desktop/mobile apps that connect to the running Python backend

The GUI applications need the Python core running as the backend server.

## 📦 Python packages (PyPI)

IoTSploit is distributed as several packages on [PyPI](https://pypi.org/). The
usual entry point is **`iotsploit-cli`** — installing it pulls in the interactive
shell and the official component stack (`iotsploit-core`, `iotsploit-django`,
`iotsploit-drivers`, `iotsploit-exploits`, `iotsploit-mcp`, `iotsploit-priv`).

| Package | Role | Location in this repo |
|---------|------|------------------------|
| **`iotsploit-cli`** | Console script `iotsploit`, Cmd2 shell, and command modules | `iotsploit-cli/` |
| **`iotsploit-core`** | Core framework, plugin system, and domain logic | `iotsploit-core/` |
| **`iotsploit-django`** | Django ring: HTTP/WebSocket APIs, ORM, Celery, backend composition | `iotsploit-django/` |
| **`iotsploit-mcp`** | MCP runtime (stdio server, WebSocket bridge, tooling integration) | `iotsploit-mcp/` |
| **`iotsploit-drivers`** | Official device drivers (registered via `iotsploit.device_drivers` entry points) | `iotsploit-drivers/` |
| **`iotsploit-exploits`** | Official security-testing plugins (registered via `iotsploit.exploit_plugins` entry points) | `iotsploit-exploits/` |
| **`iotsploit-fuzzer`** | Fuzzing library: outbound harnesses for the device under test, inbound parser fuzzing | `iotsploit-fuzzer/` |
| **`iotsploit-platforms`** | Platform-specific adapters (WiFi, Input, SSH backends) | `iotsploit-platforms/` |
| **`iotsploit-priv`** | Bounded privileged-operation client used by CLI and Django | `iotsploit-priv/` |
| **`iotsploit-protocols`** | Automotive protocol clients and parsers (SOME/IP, DoIP/UDS, AUTOSAR ARXML) | `iotsploit-protocols/` |

For day-to-day use you only need **`pip install iotsploit-cli`**; dependency
resolution brings in the rest. Advanced integrations can depend on individual
packages (for example `iotsploit-core` plus `iotsploit-django` only):

```bash
pip install iotsploit-cli        # interactive shell (pulls in the rest)
pip install iotsploit-core       # core framework & plugin system
pip install iotsploit-django     # HTTP/WebSocket backend
pip install iotsploit-mcp        # MCP runtime
pip install iotsploit-drivers    # official device drivers
pip install iotsploit-exploits   # official security-testing plugins
pip install iotsploit-fuzzer     # fuzzing library
pip install iotsploit-protocols  # automotive protocol clients
pip install 'iotsploit-django[platforms]'  # platform backends (WiFi, Input, SSH)
pip install 'iotsploit-django[distributed]' # Celery + Redis for distributed mode
```

## 🔍 What IoTSploit can find

- **Vulnerability detection** — built-in tools for common IoT device
  vulnerabilities across protocols and interfaces
- **Fuzzing** — outbound CAN/UART/SPI harnesses for hardware, inbound parser
  fuzzing that runs anywhere
- **Protocol coverage** — UART, JTAG, BLE, CAN Bus, SPI, I2C, USB, WiFi, plus
  automotive protocols (SOME/IP, DoIP/UDS)
- **Automated, repeatable tests** — plugin-based architecture, replays saved
  batches

## 🧠 How it's designed

- **Modular plugin system** — swap in testing scripts and hardware modules per
  scenario; custom Python plugins get automatic UI generation and real-time status
- **Ports-and-adapters architecture** — `iotsploit-core` defines interfaces; other
  packages implement them. Core never imports Django, Celery, Redis, or
  OS-specific libraries. See `docs/architecture.md`
- **Cross-platform** — Cmd2-powered REPL, Flutter desktop apps for Windows /
  macOS / Linux, and iOS + Android remote control apps

### Hardware Modularity

The M.2 Key E slot enables diverse hardware modules:

- **IoTSploit Motherboard**: 100M Ethernet Switch, USB 2.0 HUB, 3 M.2 Key E Slots
- **LPC4330 Board**: USB simulation capabilities, Bad USB attacks
- **ESP32 Board**: WiFi and Bluetooth-based security assessments
- **FPGA Board**: 16-channel logic analyzer with protocol decoding

## 📥 Downloads

- **Desktop**: Windows 10/11 (64-bit, MSI & portable), macOS 10.15+ (Intel &
  Apple Silicon, universal DMG), Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+; DEB,
  RPM, AppImage, Snap)
- **Mobile**: iOS (iOS 13+), Android (Android 7.0+)
- **Hardware**: firmware, drivers, schematics for IoTSploit modules

**Download all applications and resources**: [https://www.iotsploit.org/download.html](https://www.iotsploit.org/download.html)

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.10+
- Docker (optional, for the container deployment)
- Redis (only for distributed mode)
- Git (only for source development)

### 🐧 Linux (Ubuntu/Debian) system dependencies

On a fresh Linux machine, some Python dependencies may be built from source
(`pycairo`, `pygobject`, `dbus-python`, `cffi`) and require system libraries:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  pkg-config \
  cmake \
  python3-dev \
  libffi-dev \
  libcairo2-dev \
  libdbus-1-dev \
  libglib2.0-dev \
  gobject-introspection \
  libgirepository1.0-dev
```

### 1. Install IoTSploit from PyPI

Install **`iotsploit-cli`** and its dependencies (see [Python packages](#-python-packages-pypi)):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install iotsploit-cli
```

### 2. Choose a Runtime

**Local mode** is the default and needs no Redis or Celery processes. It keeps
durable execution and fuzzer state in SQLite and runs background work in bounded
threads:

```bash
export IOTSPLOIT_RUNTIME=local
```

For a **multi-process deployment**, install the distributed dependencies and provide Redis:

```bash
pip install 'iotsploit-django[distributed]'
export IOTSPLOIT_RUNTIME=distributed
docker run --name sat-redis -p 6379:6379 -d redis:latest
```

### 3. Start the Application

Launch the interactive shell:

```bash
iotsploit
```

On first start, IoTSploit initializes the local database if needed.

The default container is also local mode. Production settings require a Django
secret key; only nginx port 80 is published:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
docker compose up
```

For a non-local hostname or UI origin, also set `ALLOWED_HOSTS` and
`CORS_ALLOWED_ORIGINS`. The bundled UI must be configured to send the same API
token before mutating controls will work. Create any Django admin account
explicitly with `docker compose exec sat-toolkit python manage.py createsuperuser`.

Start the explicit distributed profile with the same variables:

```bash
IOTSPLOIT_RUNTIME=distributed docker compose --profile distributed up
```

### 4. Start Backend Services for the GUI

From inside the shell:

```text
<IoX_SHELL> service start
```

Or directly from your terminal:

```bash
iotsploit --runserver
```

To listen on another IPv4 address or use different ports, pass the endpoint
options through either command form:

```text
<IoX_SHELL> service start --host 0.0.0.0 --api-port 8080 --ws-port 8081
```

```bash
iotsploit --runserver \
  --host 0.0.0.0 --api-port 8080 --ws-port 8081 \
  --mcp-host 127.0.0.1 --mcp-port 9900
```

MCP remains bound to `127.0.0.1` unless `--mcp-host` is set explicitly. Its HTTP
endpoint does not authenticate incoming requests, so protect it before binding it
to a LAN address or `0.0.0.0`. The API, WebSocket, and MCP ports must be distinct.

### 5. Development Setup from Source

```bash
git clone https://github.com/iotsploit/iotsploit.git
cd iotsploit
git fetch
git checkout -b dev origin/dev
python -m pip install poetry
poetry install
poetry run iotsploit
```

## 📖 Usage

### IoTSploit Shell Commands

IoTSploit commands follow a `resource action` grammar. The public resources are
`host`, `device`, `driver`, `firmware`, `plugin`, `target`, `service`, `wifi`,
and `config`:

```text
device list
driver status
plugin run <plugin>
plugin run-all
target select
service start
config set --log-level DEBUG
```

Use `help` for the public overview, `help <resource>` for action and argument
details, and `help --all` for advanced cmd2 commands and legacy replacements.
Old command names remain executable during the compatibility window and print a
deprecation warning.

### Example Plugin Usage

A single `.py` file with a `BasePlugin` subclass is all you need — see
[Creating Plugins](#-creating-plugins) for how to load it.

```python
import pluggy
from iotsploit_core.core.base_plugin import BasePlugin
from iotsploit_core.core.exploit_spec import ExploitResult

hookimpl = pluggy.HookimplMarker("exploit_mgr")


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

## 🔌 Creating Plugins

IoTSploit discovers plugins through **two mechanisms**, so you can pick the one
that fits your workflow. See `docs/writing-plugins.md` for the full guide.

#### Option 1 — Load custom plugins from a directory (environment variable)

Point IoTSploit at any folder of `.py` files and it will auto-discover classes
that inherit from `BasePlugin` (exploits) or `BaseDeviceDriver` (drivers). This is
the fastest way to iterate on a plugin locally:

```bash
# Exploit plugins
export IOTSPLOIT_EXPLOIT_PLUGINS_DIR=/path/to/my/plugins

# Device drivers (optional, legacy alias: SAT_DEVICE_PLUGINS_DIR)
export IOTSPLOIT_DEVICE_PLUGINS_DIR=/path/to/my/drivers
```

Each `.py` file (except `__init__.py`) is scanned recursively for a `BasePlugin` /
`BaseDeviceDriver` subclass. See [Example Plugin Usage](#example-plugin-usage) for
a minimal plugin file.

#### Option 2 — Publish as an installable package (entry points)

For plugins you want to distribute or reuse across machines, create a Python
package and register it under the `iotsploit.exploit_plugins` (or
`iotsploit.device_drivers`) entry-point group in your `pyproject.toml`:

```toml
[tool.poetry.plugins."iotsploit.exploit_plugins"]
my_plugin = "my_pkg.my_module:MyPlugin"
```

Then `pip install` your package and IoTSploit will discover it automatically. The
official packages `iotsploit-exploits` and `iotsploit-drivers` use exactly this
mechanism — see [`iotsploit-exploits/pyproject.toml`](iotsploit-exploits/pyproject.toml) for a working example.

#### Plugin checklist

1. **Base class**: Inherit from `BasePlugin` and implement the `execute()` hook
2. **Metadata**: Provide `Name`, `Description`, `Parameters`, etc. in the `super().__init__()` info dict
3. **Documentation**: Include clear parameter descriptions and usage examples
4. **Testing**: Test your plugin thoroughly with different target configurations

## 🤝 How to Contribute

### 🐛 Reporting Issues

1. **Search existing issues** first to avoid duplicates
2. **Use the issue templates** when creating new issues
3. **Provide detailed information** including steps to reproduce, expected vs
   actual behavior, system information (OS, Python version), and relevant logs

### 💻 Contributing Code

1. **Fork the repository** and create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Follow the coding standards**: PEP 8, docstrings, type hints, unit tests
3. **Test your changes**:
   ```bash
   # Run existing tests
   python -m pytest

   # Test your plugin
   poetry run iotsploit
   ```
4. **Submit a Pull Request** with a clear description, related issue references,
   passing tests, and documentation updates

### 📚 Documentation

- **Wiki contributions**: Help improve our [documentation](https://www.iotsploit.org/)
- **Code comments**: Add clear comments to complex code sections
- **Examples**: Provide usage examples and tutorials

### 💬 Community

- **GitHub Discussions**: Participate in community discussions
- **Code Review**: Help review pull requests from other contributors
- **Feature Requests**: Suggest new features and improvements

For more detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## 🌟 Community & Support

- **Website**: [https://www.iotsploit.org/](https://www.iotsploit.org/)
- **Documentation**: [IoTSploit Wiki](https://www.iotsploit.org/)
- **GitHub**: [IoTSploit Repository](https://github.com/iotsploit/iotsploit)
- **Issues**: [Report bugs and request features](https://github.com/iotsploit/iotsploit/issues)

## 📄 License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0).

## 🙏 Acknowledgments

IoTSploit is developed and maintained by the IoTSploit community. We thank all
contributors who help make this project better.

---

**⚠️ Disclaimer**: IoTSploit is intended for authorized security testing and
educational purposes only. Users are responsible for complying with applicable
laws and regulations. The developers assume no liability for misuse of this
software.