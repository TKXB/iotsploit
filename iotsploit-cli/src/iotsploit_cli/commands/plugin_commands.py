#!/usr/bin/env python

import cmd2
from cmd2 import ansi
from .base_commands import BaseCommands
from iotsploit_cli import output
from iotsploit_core.core.exploit_spec import ExploitResult
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger

logger = iots_logger.get_logger(__name__)


class PluginCommands(BaseCommands):
    """Plugin-related commands for the SAT Shell"""

    def _show_plugin_result(self, name, success, message, data=None):
        """One result block: a marked headline, the message, then any data."""
        mark = ansi.style(f"✓ {name}", fg=ansi.Fg.GREEN) if success else ansi.style(f"✗ {name}", fg=ansi.Fg.RED)
        self.poutput(mark)
        if message:
            self.poutput(f"  {message}")
        if data not in (None, "", {}, []):
            import json
            for line in json.dumps(data, indent=2, default=str).splitlines():
                self.poutput(f"  {line}")

    @cmd2.with_category('Plugin Commands')
    def do_list_plugins(self, arg):
        'List all available plugins'
        plugins = self.plugin_manager.list_plugins()

        if not plugins:
            self.poutput("No plugins available.")
            return

        rows = []
        available_count = 0
        for plugin in plugins:
            availability = self.plugin_manager.plugin_availability(plugin)
            available_count += bool(availability.available)
            description = self.plugin_manager.plugin_registry[plugin].get("description", "")
            rows.append([
                plugin,
                output.available_mark(availability.available, availability.reason),
                description,
            ])
        self.poutput(output.table(["PLUGIN", "AVAILABLE", "DESCRIPTION"], rows, maximums=[None, None, 60]))
        self.poutput(f"{len(plugins)} plugins · {available_count} available")

    do_lsp = do_list_plugins

    @cmd2.with_category('Plugin Commands')
    def do_execute_plugin(self, arg):
        'Execute a specific plugin'
        plugins = self.plugin_manager.list_plugins()
        
        if not plugins:
            self.poutput("No plugins available to execute.")
            return

        if not arg:
            choice = Input_Mgr.Instance().single_choice(
                "Please select a plugin to execute",
                plugins
            )
        else:
            # cmd2 hands us a Statement, not a str. It compares equal to its own
            # text but hashes a tuple containing a list, so using it as a dict
            # key later raises TypeError. Flatten it here.
            choice = str(arg).strip()

        if choice not in plugins:
            self.perror(f"Plugin '{choice}' not found.")
            return

        availability = self.plugin_manager.plugin_availability(choice)
        if not availability.available:
            message = availability.reason
            if availability.hint:
                message = f"{message} {availability.hint}"
            self.perror(message)
            return

        self.poutput(ansi.style(f"Executing plugin: {choice}", fg=ansi.Fg.CYAN))
        try:
            # Get the plugin instance to access its parameters
            plugin_instance = self.plugin_manager.get_plugin(choice)
            if not plugin_instance:
                self.perror(f"Could not get plugin instance for '{choice}'")
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

            # Execute with target (device info) and parameters (plugin inputs) kept
            # separate. The interaction port is already bound by the shell, so a
            # plugin that prompts mid-run reaches this terminal without anything
            # extra here.
            result = self.plugin_manager.execute_plugin(
                choice,
                target=target_dict,
                parameters=parameters,
            )
            
            # Check if this is an async execution
            if isinstance(result, dict) and result.get('execution_type') == 'async':
                task_id = result.get('task_id')
                self.poutput(ansi.style(f"Plugin running asynchronously with task ID: {task_id}", fg=ansi.Fg.CYAN))

                # Ask user if they want to wait for results
                wait_for_results = Input_Mgr.Instance().yes_no_input(
                    "Do you want to wait for the asynchronous task to complete?",
                    default=True
                )

                if wait_for_results:
                    try:
                        import time
                        from iotsploit_django.adapters.django.interaction.models import (
                            ExecutionStatus,
                            PluginExecution,
                        )

                        start_time = time.time()
                        self.poutput("Waiting for task to complete...")

                        execution = None
                        while True:
                            execution = PluginExecution.objects.filter(
                                execution_id=task_id
                            ).first()
                            if execution is None or execution.is_terminal:
                                break
                            time.sleep(0.5)
                            if time.time() - start_time > 300:  # 5 minutes
                                self.pwarning("Timeout waiting for task to complete")
                                return

                        final_result = (
                            execution.result or execution.error
                            if execution is not None
                            else {"status": "error", "message": "Execution not found"}
                        )
                        if isinstance(final_result, dict):
                            self._show_plugin_result(
                                choice,
                                execution is not None
                                and execution.status == ExecutionStatus.COMPLETED
                                and final_result.get("status") != "error"
                                and final_result.get("success", True),
                                final_result.get("message", ""),
                                {k: v for k, v in final_result.items() if k not in ("status", "message")},
                            )
                        else:
                            self._show_plugin_result(
                                choice,
                                execution.status == ExecutionStatus.COMPLETED,
                                str(final_result),
                            )

                    except Exception as e:
                        self.perror(f"Error getting async result: {str(e)}")
                        logger.debug("Detailed error:", exc_info=True)
                else:
                    self.poutput(f"Task {task_id} is running in the background.")

            elif isinstance(result, ExploitResult):
                self._show_plugin_result(choice, result.success, result.message, result.data)
            else:
                self._show_plugin_result(choice, True, str(result))
        except Exception as e:
            self.perror(f"Error executing plugin: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    do_exec = do_execute_plugin

    @cmd2.with_category('Plugin Commands')
    def do_flash_plugins(self, arg):
        'Refresh and reload all plugins from installed packages and entry points'
        try:
            initial_plugins = len(self.plugin_manager.list_plugins())
            self.plugin_manager.auto_discover_plugins()
            final_plugins = len(self.plugin_manager.list_plugins())

            if final_plugins > initial_plugins:
                self.poutput(ansi.style(f"Added {final_plugins - initial_plugins} plugins.", fg=ansi.Fg.GREEN))
            elif final_plugins < initial_plugins:
                self.poutput(ansi.style(f"Removed {initial_plugins - final_plugins} plugins.", fg=ansi.Fg.YELLOW))
            else:
                self.poutput("No changes.")
            self.poutput(f"{final_plugins} plugins installed. Use 'plugin list' to see them.")
        except Exception as e:
            self.perror(f"Error refreshing plugins: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    do_fp = do_flash_plugins
