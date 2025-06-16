#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from .base_commands import BaseCommands
from sat_toolkit.core.exploit_spec import ExploitResult
from sat_toolkit.tools.input_mgr import Input_Mgr
from sat_toolkit.tools.xlogger import xlog as logger


class SystemCommands(BaseCommands):
    """System-related commands for the SAT Shell"""

    @cmd2.with_category('System Commands')
    def do_exploit(self, arg):
        'Execute all plugins in the IotSploit System'
        logger.info(ansi.style("Executing all plugins in the IotSploit System", fg=ansi.Fg.CYAN))
        
        results = self.plugin_manager.exploit()
        
        if not results:
            logger.warning(ansi.style("No results returned from any plugins", fg=ansi.Fg.YELLOW))
        else:
            # Log the results
            for plugin_name, result in results.items():
                if result is None:
                    logger.warning(ansi.style(f"Plugin {plugin_name} returned no result", fg=ansi.Fg.YELLOW))
                elif isinstance(result, ExploitResult):
                    logger.info(ansi.style(f"Plugin {plugin_name} execution result:", fg=ansi.Fg.GREEN))
                    logger.info(f"Success: {result.success}")
                    logger.info(f"Message: {result.message}")
                    logger.info(f"Data: {result.data}")
                else:
                    logger.info(ansi.style(f"Plugin {plugin_name} execution result:", fg=ansi.Fg.GREEN))
                    logger.info(str(result))
        
        logger.info(ansi.style("Exploit execution completed", fg=ansi.Fg.CYAN))

    @cmd2.with_category('System Commands')
    def do_exit(self, arg):
        'Exit Console'
        if self.django_server_process:
            self.do_stop_server(arg)
        self._cleanup_devices()
        logger.info("IotSploit Shell Quit. ByeBye~")
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
                logger.error(ansi.style(f"Invalid log level. Choose from: {', '.join(valid_levels)}", fg=ansi.Fg.RED))
                return

        try:
            # Set the log level using XLogger's set_level method
            logger.set_level(selected_level)
            logger.info(ansi.style(f"Log level set to {selected_level}", fg=ansi.Fg.GREEN))
        except Exception as e:
            logger.error(ansi.style(f"Error setting log level: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    # Add an alias for set_log_level
    do_sll = do_set_log_level 