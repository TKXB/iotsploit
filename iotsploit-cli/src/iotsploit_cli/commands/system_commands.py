#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import os
from .base_commands import BaseCommands
from iotsploit_core.core.exploit_spec import ExploitResult
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_django.tools.xlogger import xlog
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class SystemCommands(BaseCommands):
    """System-related commands for the SAT Shell"""

    @cmd2.with_category('System Commands')
    def do_exploit(self, arg):
        'Execute all plugins in the IotSploit System'
        results = self.plugin_manager.exploit()

        if not results:
            self.poutput("No results returned from any plugins.")
            return
        for plugin_name, result in results.items():
            if result is None:
                self.poutput(ansi.style(f"✗ {plugin_name}", fg=ansi.Fg.YELLOW) + " returned no result")
            elif isinstance(result, ExploitResult):
                mark = ansi.style(f"✓ {plugin_name}", fg=ansi.Fg.GREEN) if result.success \
                    else ansi.style(f"✗ {plugin_name}", fg=ansi.Fg.RED)
                self.poutput(mark + (f"  {result.message}" if result.message else ""))
            else:
                self.poutput(ansi.style(f"✓ {plugin_name}", fg=ansi.Fg.GREEN) + f"  {result}")

    @cmd2.with_category('System Commands')
    def do_exit(self, arg):
        'Exit Console'
        if self.django_server_process:
            self.do_stop_server(arg)
        self.poutput("IoTSploit shell closed.")
        return True

    @cmd2.with_category('System Commands')
    def do_set_log_level(self, arg):
        'Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)'
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
        if not arg:
            # If no argument provided, let user select from valid levels
            selected_level = Input_Mgr.Instance().single_choice(
                "Select logging level",
                valid_levels
            )
        else:
            # If argument provided, validate it
            selected_level = arg.upper()
            if selected_level not in valid_levels:
                self.perror(f"Invalid log level. Choose from: {', '.join(valid_levels)}")
                return

        try:
            # Set the log level via core logger (affects all core-managed loggers)
            iots_logger.set_level(selected_level)
            self.poutput(ansi.style(f"Log level set to {selected_level}", fg=ansi.Fg.GREEN))
        except Exception as e:
            self.perror(f"Error setting log level: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for set_log_level
    do_sll = do_set_log_level

    @cmd2.with_category('System Commands')
    def do_set_log_format(self, arg):
        'Set the terminal logging format (standard, compact, plain)'
        valid_formats = ['standard', 'compact', 'plain']

        if not arg:
            selected_format = Input_Mgr.Instance().single_choice(
                "Select terminal log format",
                valid_formats
            )
        else:
            selected_format = arg.strip().lower()
            if selected_format not in valid_formats:
                self.perror(f"Invalid log format. Choose from: {', '.join(valid_formats)}")
                return

        try:
            os.environ["IOTSPLOIT_LOG_FORMAT"] = selected_format
            iots_logger.set_format(selected_format)
            xlog.set_format(selected_format)
            self.poutput(ansi.style(f"Log format set to {selected_format}", fg=ansi.Fg.GREEN))
        except Exception as e:
            self.perror(f"Error setting log format: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for set_log_format
    do_slf = do_set_log_format
