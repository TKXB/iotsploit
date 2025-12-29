"""AI assistant websocket consumer (migrated from `sat_toolkit`)."""

# Stage-5: keep behavior stable by re-exporting the legacy consumer.
from sat_toolkit.websocket.ai_assistant_consumer import AIAssistantConsumer  # noqa: F401

__all__ = ["AIAssistantConsumer"]


