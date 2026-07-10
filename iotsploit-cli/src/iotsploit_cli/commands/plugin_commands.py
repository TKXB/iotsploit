#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from .base_commands import BaseCommands
from iotsploit_core.core.exploit_spec import ExploitResult
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class PluginCommands(BaseCommands):
    """Plugin-related commands for the SAT Shell"""

    @cmd2.with_category('Plugin Commands')
    def do_list_plugins(self, arg):
        'List all available plugins'
        plugins = self.plugin_manager.list_plugins()
        
        if plugins:
            logger.info(ansi.style("Available plugins:", fg=ansi.Fg.CYAN))
            for plugin in plugins:
                logger.info(ansi.style(f"  - {plugin}", fg=ansi.Fg.CYAN))
        else:
            logger.info(ansi.style("No plugins available.", fg=ansi.Fg.YELLOW))

    do_lsp = do_list_plugins

    @cmd2.with_category('Plugin Commands')
    def do_execute_plugin(self, arg):
        'Execute a specific plugin'
        plugins = self.plugin_manager.list_plugins()
        
        if not plugins:
            logger.info(ansi.style("No plugins available to execute.", fg=ansi.Fg.YELLOW))
            return

        if not arg:
            choice = Input_Mgr.Instance().single_choice(
                "Please select a plugin to execute",
                plugins
            )
        else:
            choice = arg

        if choice not in plugins:
            logger.error(ansi.style(f"Plugin '{choice}' not found.", fg=ansi.Fg.RED))
            return

        logger.info(ansi.style(f"Executing plugin: {choice}", fg=ansi.Fg.CYAN))
        try:
            # Get the plugin instance to access its parameters
            plugin_instance = self.plugin_manager.get_plugin(choice)
            if not plugin_instance:
                logger.error(ansi.style(f"Could not get plugin instance for '{choice}'", fg=ansi.Fg.RED))
                return
                
            # Get plugin info with parameters
            plugin_info = plugin_instance.get_info()
            plugin_params = plugin_info.get('Parameters', {})
            
            # Get current target from target manager
            target_manager = self.target_manager
            current_target = target_manager.get_current_target()
            
            # Prepare target dictionary (device/target info only, e.g. ip_address)
            target_dict = {}
            if current_target:
                target_dict = current_target.get_info() if hasattr(current_target, 'get_info') else {}

            # Collect the plugin's declared parameters separately from the target.
            # Plugins read their params from `parameters` (not `target`), so these
            # must be passed as parameters=, matching the HTTP/GUI execute path.
            # We prompt for every declared parameter (not only required ones) so the
            # TUI mirrors the GUI. Each prompt is labeled REQUIRED or optional:
            #   - required  -> the user must enter a non-empty value.
            #   - optional  -> the declared default is shown; pressing Enter skips it.
            parameters = {}
            for param_name, param_info in plugin_params.items():
                # Skip params already satisfied by the current target
                if param_name in target_dict:
                    continue

                param_type = param_info.get('type', 'str')
                required = param_info.get('required', False)
                description = param_info.get('description', f"Enter {param_name}")
                default = param_info.get('default')
                validation = param_info.get('validation', {})

                # Label so the user knows whether the field is mandatory or skippable
                if required:
                    prompt = f"{description} (REQUIRED)"
                elif default is not None:
                    prompt = f"{description} (optional, default: {default}, press Enter to skip)"
                else:
                    prompt = f"{description} (optional, press Enter to skip)"

                if param_type == 'int':
                    min_val = validation.get('min')
                    max_val = validation.get('max')
                    value = Input_Mgr.Instance().int_input(
                        prompt,
                        default=default if isinstance(default, int) else None,
                        min_val=min_val,
                        max_val=max_val
                    )
                elif param_type == 'bool':
                    value = Input_Mgr.Instance().yes_no_input(
                        prompt,
                        default=bool(default) if default is not None else True
                    )
                elif param_type == 'str' and 'choices' in validation:
                    value = Input_Mgr.Instance().single_choice(
                        f"{prompt} (Choose one)",
                        validation['choices']
                    )
                elif required:
                    # Mandatory free-text: re-prompt until the user enters something
                    value = Input_Mgr.Instance().string_input(
                        prompt,
                        verify_func=lambda s: bool(s and s.strip())
                    )
                else:
                    # Optional free-text: empty input skips the field. Fall back to the
                    # declared default if there is one, otherwise omit it entirely so
                    # the plugin applies its own default.
                    value = Input_Mgr.Instance().string_input(prompt)
                    if value is None or value == "":
                        if default is not None:
                            value = default
                        else:
                            continue

                parameters[param_name] = value

            logger.debug(f"Executing plugin '{choice}' with target={target_dict}, parameters={parameters}")

            # Execute with target (device info) and parameters (plugin inputs) kept separate
            result = self.plugin_manager.execute_plugin(choice, target=target_dict, parameters=parameters)
            
            # Check if this is an async execution
            if isinstance(result, dict) and result.get('execution_type') == 'async':
                task_id = result.get('task_id')
                logger.info(ansi.style(f"Plugin running asynchronously with task ID: {task_id}", fg=ansi.Fg.CYAN))
                
                # Ask user if they want to wait for results
                wait_for_results = Input_Mgr.Instance().yes_no_input(
                    "Do you want to wait for the asynchronous task to complete?",
                    default=True
                )
                
                if wait_for_results:
                    # Import celery here to avoid circular imports
                    try:
                        from celery.result import AsyncResult
                        from iotsploit_django.tasks import celery_app
                        import time

                        task_result = AsyncResult(task_id, app=celery_app)
                        
                        # Poll for results with a progress bar
                        progress = 0
                        start_time = time.time()
                        
                        logger.info(ansi.style("Waiting for task to complete...", fg=ansi.Fg.CYAN))
                        
                        while not task_result.ready():
                            # Try to get progress information
                            task_info = task_result.info
                            
                            if isinstance(task_info, dict):
                                new_progress = task_info.get('progress', 0)
                                message = task_info.get('message', 'Processing...')
                                
                                # Only update if progress has changed
                                if new_progress != progress:
                                    progress = new_progress
                                    # Print progress bar
                                    bar_length = 50
                                    filled_length = int(bar_length * progress / 100)
                                    bar = '█' * filled_length + '-' * (bar_length - filled_length)
                                    logger.info(f"Progress: [{bar}] {progress:.1f}% - {message}")
                            
                            # Sleep briefly before checking again
                            time.sleep(0.5)
                            
                            # Add a timeout to prevent infinite waiting
                            if time.time() - start_time > 300:  # 5 minutes
                                logger.warning(ansi.style("Timeout waiting for task to complete", fg=ansi.Fg.YELLOW))
                                break
                        
                        # Get final result
                        final_result = task_result.get(timeout=5)  # 5 second timeout for final result
                        
                        logger.info(ansi.style("Async plugin execution completed", fg=ansi.Fg.GREEN))
                        if isinstance(final_result, dict):
                            logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                            for key, value in final_result.items():
                                logger.info(f"{key}: {value}")
                        else:
                            logger.info(f"Result: {final_result}")
                    
                    except ImportError as e:
                        logger.error(ansi.style(f"Error importing Celery modules: {str(e)}", fg=ansi.Fg.RED))
                    except Exception as e:
                        logger.error(ansi.style(f"Error getting async result: {str(e)}", fg=ansi.Fg.RED))
                        logger.debug("Detailed error:", exc_info=True)
                
                # Display initial async info regardless
                logger.info(ansi.style("Initial async task info:", fg=ansi.Fg.GREEN))
                logger.info(str(result))
                
            elif isinstance(result, ExploitResult):
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(f"Success: {result.success}")
                logger.info(f"Message: {result.message}")
                logger.info(f"Data: {result.data}")
            else:
                logger.info(ansi.style("Plugin execution result:", fg=ansi.Fg.GREEN))
                logger.info(str(result))
        except Exception as e:
            logger.error(ansi.style(f"Error executing plugin: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    do_exec = do_execute_plugin

    @cmd2.with_category('Plugin Commands')
    def do_flash_plugins(self, arg):
        'Refresh and reload all plugins from installed packages and entry points'
        try:
            logger.info(ansi.style("Starting plugin refresh...", fg=ansi.Fg.CYAN))
            
            # Get current plugin count
            initial_plugins = len(self.plugin_manager.list_plugins())
            
            # Run auto-discovery
            self.plugin_manager.auto_discover_plugins()
            
            # Get new plugin count
            final_plugins = len(self.plugin_manager.list_plugins())
            
            # Calculate changes
            if final_plugins > initial_plugins:
                logger.info(ansi.style(
                    f"Plugin refresh complete! Added {final_plugins - initial_plugins} new plugins.", 
                    fg=ansi.Fg.GREEN
                ))
            elif final_plugins < initial_plugins:
                logger.info(ansi.style(
                    f"Plugin refresh complete! Removed {initial_plugins - final_plugins} plugins.", 
                    fg=ansi.Fg.YELLOW
                ))
            else:
                logger.info(ansi.style(
                    "Plugin refresh complete! No changes detected.", 
                    fg=ansi.Fg.CYAN
                ))
            
            # Display current plugins
            logger.info(ansi.style("\nCurrent plugins:", fg=ansi.Fg.CYAN))
            for plugin in self.plugin_manager.list_plugins():
                logger.info(ansi.style(f"  - {plugin}", fg=ansi.Fg.CYAN))
                
        except Exception as e:
            logger.error(ansi.style(f"Error refreshing plugins: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)

    do_fp = do_flash_plugins
