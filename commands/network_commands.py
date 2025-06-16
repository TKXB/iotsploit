#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import time
from .base_commands import BaseCommands
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.xlogger import xlog as logger


class NetworkCommands(BaseCommands):
    """Network-related commands for the SAT Shell"""

    @cmd2.with_category('Network Commands')
    def do_connect_wifi(self, arg):
        'Connect to WiFi network by providing SSID and password'
        logger.info(ansi.style("WiFi Connection Setup", fg=ansi.Fg.CYAN))
        
        # Get SSID from user
        ssid = Input_Mgr.Instance().string_input("Enter WiFi SSID")
        
        # Get password from user
        password = Input_Mgr.Instance().string_input("Enter WiFi password")
        
        # Attempt to connect
        logger.info(ansi.style(f"Attempting to connect to {ssid}...", fg=ansi.Fg.CYAN))
        WiFi_Mgr.Instance().sta_connect_wifi(ssid, password)
        
        # Wait for connection to establish
        time.sleep(2)
        
        # Show connection status
        WiFi_Mgr.Instance().status()
