#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import time
from .base_commands import BaseCommands
from iotsploit_platforms import get_shared_wifi_backend
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class NetworkCommands(BaseCommands):
    """Network-related commands for the SAT Shell"""

    @cmd2.with_category('Network Commands')
    def do_connect_wifi(self, arg):
        'Connect to WiFi network by providing SSID and password'
        self.poutput(ansi.style("WiFi Connection Setup", fg=ansi.Fg.CYAN))
        
        # Get SSID from user
        ssid = Input_Mgr.Instance().string_input("Enter WiFi SSID")
        
        # Get password from user
        password = Input_Mgr.Instance().string_input("Enter WiFi password")
        
        # Attempt to connect
        self.poutput(f"Attempting to connect to {ssid}...")
        wifi_backend = get_shared_wifi_backend()
        try:
            wifi_backend.sta_connect(str(ssid), str(password))
        except Exception as e:
            self.perror(f"WiFi connection failed: {e}")

        # Wait for connection to establish
        time.sleep(2)

        # Show connection status
        wifi_backend.status()
