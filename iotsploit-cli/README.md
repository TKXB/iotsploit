# iotsploit-cli

IoTSploit interactive CLI shell for IoT security testing.

## Overview

This package provides the `iotsploit` command-line shell built on top of `cmd2`.
It bundles the core console loop (`console.py`) and all command modules
(`commands/`) that implement device management, plugin execution, target
management, network operations, and more.

## Installation

```bash
pip install iotsploit-cli
```

## Usage

```bash
iotsploit
```

Or with the Django server started immediately:

```bash
iotsploit --runserver
```

## License

GPL-3.0-or-later. See [LICENSE](../LICENSE) for details.
For commercial use, contact wang3919379@gmail.com.
