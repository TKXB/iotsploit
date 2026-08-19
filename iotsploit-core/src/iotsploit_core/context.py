"""
Plugin Context for Backend Injection.

This module provides a typed context object for injecting platform-specific
backends into plugins. This avoids magic string keys and provides better
type safety and IDE support.
"""

from dataclasses import dataclass
from typing import Optional

from iotsploit_core.core.interaction_binding import current_interaction
from iotsploit_core.ports.interaction import InteractionPort, InteractionUnavailable
from iotsploit_core.ports.wifi_backend import WifiBackend


@dataclass
class PluginContext:
    """
    Context object for injecting platform-specific backends into plugins.
    
    This provides a structured way to pass backends to plugins, avoiding
    dictionary-based injection with magic string keys. As new backends are
    added, they can be added as optional fields here.
    
    Attributes:
        wifi: Optional WiFi backend instance
    """
    wifi: Optional[WifiBackend] = None

    @property
    def interaction(self) -> InteractionPort:
        """The interaction port for the running execution.

        Resolved on every access rather than stored, because this context is
        injected once per cached plugin instance while the port is scoped to a
        single execution. See ``core.interaction_binding``.

        Raises:
            InteractionUnavailable: when no execution has bound a port, e.g. a
                plugin that prompts but was started outside the execution
                lifecycle.
        """
        port = current_interaction()
        if port is None:
            raise InteractionUnavailable(
                "No interaction broker is bound to this execution. Interactive "
                "plugins must be run through the execution lifecycle (the "
                "interactive Celery queue, or the CLI console adapter)."
            )
        return port

    @property
    def has_interaction(self) -> bool:
        """Whether a prompt can be raised right now, without raising."""
        return current_interaction() is not None
