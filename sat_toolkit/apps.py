from django.apps import AppConfig
import os
import logging
import sys

logger = logging.getLogger(__name__)


class SatToolkitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sat_toolkit'
    
    def ready(self):
        """
        Initialize the application when Django starts.
        This method is called once per application instance.
        """
        # Avoid starting long-running background services during unit tests.
        if any(arg in ("test", "pytest") for arg in sys.argv):
            return

        # Avoid running twice in development (runserver spawns a reloader process)
        # Only run in the main process (when RUN_MAIN is set)
        if os.environ.get('RUN_MAIN') == 'true' or os.environ.get('RUN_MAIN') is None:
            try:
                from django.conf import settings
                from sat_toolkit.tools.discovery_server import start_discovery_server
                # Wire StreamManager backend (Ports & Adapters): core should not import adapters.
                try:
                    from iotsploit_core.core.stream_manager import StreamManager
                    from sat_toolkit.adapters.django.stream_manager import DjangoStreamBackend

                    StreamManager.configure_backend(DjangoStreamBackend())
                except Exception:
                    # If channels/redis isn't available/configured, keep Noop backend.
                    pass
                
                # Check if discovery is enabled
                if getattr(settings, 'DISCOVERY_ENABLED', True):
                    port = getattr(settings, 'DISCOVERY_UDP_PORT', 37020)
                    
                    # Start the UDP discovery server
                    # Use port 8888 for HTTP and 9999 for WebSocket (Daphne)
                    start_discovery_server(port=port, http_port=8888, ws_port=9999)
                    logger.info(f"UDP Discovery Server initialized on port {port}")
                else:
                    logger.info("UDP Discovery Server is disabled in settings")
            except Exception as e:
                logger.error(f"Failed to start UDP Discovery Server: {e}")
                # Don't fail the application startup if discovery server fails
                pass
