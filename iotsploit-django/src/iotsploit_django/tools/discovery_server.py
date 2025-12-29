"""
UDP Discovery Server for SAT Toolkit

This module provides a UDP-based server discovery mechanism that allows
Flutter clients to automatically find the server on the local network.
"""

import socket
import json
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DiscoveryServer:
    """
    UDP server that listens for discovery requests and responds with server information.
    
    The server listens on a specified UDP port for broadcast messages containing
    'SAT_DISCOVERY_REQUEST' and responds with server configuration information.
    """
    
    DISCOVERY_REQUEST = 'SAT_DISCOVERY_REQUEST'
    BUFFER_SIZE = 1024
    
    def __init__(self, port: int = 37020, http_port: int = 8888, ws_port: int = 9999):
        """
        Initialize the discovery server.
        
        Args:
            port: UDP port to listen on for discovery requests
            http_port: HTTP API port of the Django server
            ws_port: WebSocket port (Daphne server)
        """
        self.port = port
        self.http_port = http_port
        self.ws_port = ws_port
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.socket: Optional[socket.socket] = None
        
    def start(self):
        """Start the discovery server in a background thread."""
        if self.running:
            logger.warning("Discovery server is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        logger.info(f"Discovery server started on UDP port {self.port}")
        
    def _listen(self):
        """Main listening loop that handles discovery requests."""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to all interfaces
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.settimeout(1.0)  # 1 second timeout for graceful shutdown
            
            logger.info(f"Discovery server listening on 0.0.0.0:{self.port}")
            
            while self.running:
                try:
                    # Receive data
                    data, addr = self.socket.recvfrom(self.BUFFER_SIZE)
                    message = data.decode('utf-8', errors='ignore').strip()
                    
                    logger.debug(f"Received discovery request from {addr}: {message}")
                    
                    # Check if it's a valid discovery request
                    if message == self.DISCOVERY_REQUEST:
                        # Prepare response
                        response = {
                            'server_name': 'SAT-Toolkit',
                            'http_port': self.http_port,
                            'ws_port': self.ws_port,
                            'version': '1.0.0'
                        }
                        
                        # Send response back to the client
                        response_data = json.dumps(response).encode('utf-8')
                        self.socket.sendto(response_data, addr)
                        
                        logger.info(f"Sent discovery response to {addr[0]}:{addr[1]}")
                    else:
                        logger.debug(f"Ignoring invalid discovery request: {message}")
                        
                except socket.timeout:
                    # Timeout is expected, continue listening
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error handling discovery request: {e}")
                    
        except Exception as e:
            logger.error(f"Discovery server error: {e}")
        finally:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            logger.info("Discovery server stopped")
            
    def stop(self):
        """Stop the discovery server gracefully."""
        if not self.running:
            logger.warning("Discovery server is not running")
            return
        
        logger.info("Stopping discovery server...")
        self.running = False
        
        # Wait for the thread to finish (with timeout)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        
        logger.info("Discovery server stopped")


# Global instance
_discovery_server_instance: Optional[DiscoveryServer] = None


def get_discovery_server() -> Optional[DiscoveryServer]:
    """Get the global discovery server instance."""
    return _discovery_server_instance


def start_discovery_server(port: int = 37020, http_port: int = 8888, ws_port: int = 9999):
    """
    Start the global discovery server instance.
    
    Args:
        port: UDP port to listen on
        http_port: HTTP API port
        ws_port: WebSocket port
    """
    global _discovery_server_instance
    
    if _discovery_server_instance is not None and _discovery_server_instance.running:
        logger.warning("Discovery server is already running")
        return _discovery_server_instance
    
    _discovery_server_instance = DiscoveryServer(port, http_port, ws_port)
    _discovery_server_instance.start()
    return _discovery_server_instance


def stop_discovery_server():
    """Stop the global discovery server instance."""
    global _discovery_server_instance
    
    if _discovery_server_instance is not None:
        _discovery_server_instance.stop()
        _discovery_server_instance = None

