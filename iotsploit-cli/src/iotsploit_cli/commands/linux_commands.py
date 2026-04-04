#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import subprocess
from .base_commands import BaseCommands
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class LinuxCommands(BaseCommands):
    """Linux system commands for the SAT Shell"""

    @cmd2.with_category('Linux Commands')
    def do_ls(self, arg):
        'List directory contents'
        try:
            result = subprocess.run(['ls'] + arg.split(), capture_output=True, text=True)
            self.poutput(result.stdout)
            if result.stderr:
                self.poutput(result.stderr)
        except Exception as e:
            logger.error(f"Error executing ls: {str(e)}")

    @cmd2.with_category('Linux Commands')
    def do_lsusb(self, arg):
        'List USB devices'
        try:
            result = subprocess.run(['lsusb'] + arg.split(), capture_output=True, text=True)
            self.poutput(result.stdout)
            if result.stderr:
                self.poutput(result.stderr)
        except Exception as e:
            logger.error(f"Error executing lsusb: {str(e)}")
