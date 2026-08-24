"""Automotive protocol clients and description parsers, free of runtime state.

Nothing here reads the IoTSploit database, environment variables, or the
current target, and nothing here runs sudo or prompts a human. Inputs are
explicit config objects or caller-selected description files. That is what
lets these run under Celery, under MCP, in a test, or from a plugin, and it is
what keeps one lab bench's IP addresses out of the library.

Importing this package is deliberately cheap: scapy costs hundreds of
milliseconds and reads host network configuration at import time, so every
scapy import lives inside the module that needs it rather than here.
"""

from __future__ import annotations

__version__ = "0.0.8"

__all__ = ["NegativeResponse", "NotConfigured", "ProtocolError"]

from iotsploit_protocols.errors import NegativeResponse, NotConfigured, ProtocolError
