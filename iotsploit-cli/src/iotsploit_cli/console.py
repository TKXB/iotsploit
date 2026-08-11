#!/usr/bin/env python
import os
import sys
import time
import importlib
import inspect
from typing import Dict
import argparse

LOG_FORMAT_CHOICES = ("standard", "compact", "plain")


def _prime_log_format_env_from_argv(argv):
    selected_format = None
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == '--plain-log' and selected_format is None:
            selected_format = "plain"
        elif arg == '--log-format' and idx + 1 < len(argv):
            selected_format = argv[idx + 1].strip().lower()
            idx += 1
        elif arg.startswith('--log-format='):
            selected_format = arg.split('=', 1)[1].strip().lower()
        idx += 1

    if selected_format in LOG_FORMAT_CHOICES:
        os.environ["IOTSPLOIT_LOG_FORMAT"] = selected_format


_prime_log_format_env_from_argv(sys.argv[1:])

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

import django
django.setup()

def ensure_database_initialized():
    """Automatically initialize database tables if they don't exist"""
    try:
        from iotsploit_django.adapters.django.plugins.models import Plugin
        Plugin.objects.exists()
        
        from sqlalchemy.exc import OperationalError
        from iotsploit_django.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db
        from iotsploit_django.adapters.django.device_models import DeviceDriverState
        
        session = get_default_sqlalchemy_db().SessionLocal()
        try:
            session.query(DeviceDriverState).first()
            session.close()
        except OperationalError as e:
            session.close()
            if "no such table: device_driver_states" in str(e):
                print("🔧 Setting up SQLAlchemy database tables...")
                db = get_default_sqlalchemy_db()
                db.Base.metadata.create_all(db.engine)
                print("✅ SQLAlchemy tables created successfully!")
            else:
                raise e
                
    except Exception as e:
        if "no such table" in str(e) or "no such column" in str(e):
            print("🔧 Database not initialized. Setting up database...")
            try:
                print("📋 Running Django migrations...")
                from django.core.management import execute_from_command_line
                execute_from_command_line(["manage.py", "migrate", "--noinput"])
                print("✅ Django migrations completed!")
                
                print("📋 Creating SQLAlchemy tables...")
                from iotsploit_django.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db
                db = get_default_sqlalchemy_db()
                db.Base.metadata.create_all(db.engine)
                print("✅ SQLAlchemy tables created!")
                
                print("🎉 Database initialization completed successfully!")
                
            except Exception as init_error:
                print(f"❌ Error initializing database: {init_error}")
                print("💡 You may need to run: python manage.py migrate")
                raise init_error
        else:
            raise e

# Initialize database before proceeding
ensure_database_initialized()

# Now it's safe to import Django and other modules
import cmd2
from cmd2 import ansi
from iotsploit_cli.command_registry import (
    ADVANCED_COMMANDS,
    ESSENTIAL_COMMANDS,
    LEGACY_REPLACEMENTS,
    RESOURCE_SPECS,
)

# Command palette imports (prompt-toolkit based live command discovery).
# Wrapped in try/except so the shell still works if prompt-toolkit is missing.
try:
    from iotsploit_cli.command_palette import (
        CommandCatalog,
        Cmd2CompletionAdapter,
        CommandPaletteCompleter,
        PaletteInputSession,
    )
    _PALETTE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PALETTE_AVAILABLE = False

from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_core.domain.target import Vehicle
from iotsploit_django.composition_root.wiring import get_device_driver_manager, get_exploit_plugin_manager
from iotsploit_django.adapters.django.device_models import DeviceManager
from iotsploit_core.domain.device import DeviceType, SerialDevice, SocketCANDevice, USBDevice
from iotsploit_django.tools.env_mgr import Env_Mgr
from iotsploit_django.tools.report_mgr import Report_Mgr
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_django.tools.xlogger import xlog as logger
from iotsploit_core.utils import iots_logger

def global_exception_handler(exctype, value, traceback):
    logger.error("Unhandled exception", exc_info=(exctype, value, traceback))

sys.excepthook = global_exception_handler

def discover_command_modules():
    """Auto-discover and load all command modules"""
    from iotsploit_cli.commands.base_commands import BaseCommands
    
    command_classes = []
    commands_dir = os.path.join(os.path.dirname(__file__), 'commands')

    for filename in os.listdir(commands_dir):
        if filename.endswith('.py') and not filename.startswith('__') and filename != 'base_commands.py':
            module_name = filename[:-3]
            
            try:
                module = importlib.import_module(f'iotsploit_cli.commands.{module_name}')

                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseCommands) and 
                        obj != BaseCommands):
                        command_classes.append(obj)
                        logger.debug(f"Discovered command class: {obj.__name__} from {module_name}")
            except ImportError as e:
                logger.warning(f"Could not import {module_name}: {e}")
            except Exception as e:
                logger.error(f"Error loading {module_name}: {e}")
    
    logger.info(f"Auto-discovered {len(command_classes)} command modules")
    return command_classes

# Auto-discover command modules
try:
    CommandMixins = discover_command_modules()
    logger.info(f"Successfully loaded command modules: {[cls.__name__ for cls in CommandMixins]}")
except Exception as e:
    logger.error(f"Failed to discover command modules: {e}")
    CommandMixins = []

# Create dynamic inheritance
SAT_Shell_Base = type('SAT_Shell_Base', (cmd2.Cmd, *CommandMixins), {})

class SAT_Shell(SAT_Shell_Base):
    intro = ansi.style('''
██╗  █████╗ ████████╗███████╗██████╗ ██╗      ██████╗ ██╗████████╗
██║██╔═══██╗╚══██╔══╝██╔════╝██╔══██╗██║     ██╔═══██╗██║╚══██╔══╝
██║██║   ██║   ██║   ███████╗██████╔╝██║     ██║   ██║██║   ██║   
██║██║   ██║   ██║   ╚════██║██╔═══╝ ██║     ██║   ██║██║   ██║   
██║╚██████╔╝   ██║   ███████║██║     ███████╗╚██████╔╝██║   ██║   
╚═╝ ╚═════╝    ╚═╝   ╚══════╝╚═╝     ╚══════╝ ╚═════╝ ╚═╝   ╚═╝   
''', fg=ansi.Fg.GREEN) + '\n' + ansi.style('Welcome to IoTSploit Shell. Type help or ? to list commands.\n', fg=ansi.Fg.YELLOW)

    prompt = ansi.style('<IoX_SHELL> ', fg=ansi.Fg.BLUE)

    def __init__(self):
        # Initialize the command categories dictionary before calling super().__init__()
        self._cmd_to_category = {}
        
        # Now call the parent class initialization
        super().__init__()
        
        # Rest of your initialization code...
        self.django_server_process = None
        self.daphne_server_process = None
        self.mcp_bridge_process = None
        self.celery_worker_process = None
        
        # Initialize device manager and connected devices
        self.device_driver_manager = get_device_driver_manager()
        # 初始化设备相关属性
        self._current_plugin = None
        self._current_device = None
        self._current_driver = None
        self.connected_devices = {}
        
        
        # Initialize plugin manager
        # Use Django composition root to wire ORM repos (+ optional Celery runner).
        # Default to Celery-enabled behavior for parity with previous implementation.
        use_celery = os.getenv("SAT_SHELL_USE_CELERY", "1").lower() not in ("0", "false", "no")
        self.plugin_manager = get_exploit_plugin_manager(use_celery=use_celery)
        self.plugin_manager.initialize()
        
        # Initialize target manager
        self.target_manager = TargetManager.get_instance()
        self.target_manager.register_target("vehicle", Vehicle)
        
        # Check if database has any targets, if not, optionally load from JSON as initial setup
        existing_targets = self.target_manager.get_all_targets()
        if not existing_targets:
            logger.info("No targets found in database. You can:")
            logger.info("1. Use Flutter UI to create targets")
            logger.info("2. Use 'target_import' command to import from JSON file")
            logger.info("3. Use target management commands to create targets manually")
        else:
            logger.info(f"Found {len(existing_targets)} targets in database")
        
        # Note: Removed automatic JSON loading to prevent overwriting user changes
        # Use 'target_import conf/target.json' command if you need to import from JSON

        # Initialize device manager
        self.device_manager = DeviceManager.get_instance()
        self.device_manager.register_device(DeviceType.Serial, SerialDevice)
        self.device_manager.register_device(DeviceType.USB, USBDevice)
        self.device_manager.register_device(DeviceType.CAN, SocketCANDevice)
        
        # Note: Removed automatic JSON loading to use database as single source of truth
        # Devices are now discovered by drivers via scan() or managed through UI/CLI
        # Use 'device_import <json_file>' command if you need to import from JSON
        existing_devices = self.device_manager.get_all_devices()
        if not existing_devices:
            logger.info("No devices found in database. Devices will be auto-discovered by drivers.")
            logger.info("You can also use 'device_import conf/devices.json' to import from JSON file.")


        # Customize help display
        self.help_category_header = ansi.style("\n{:-^80}\n", fg=ansi.Fg.BLUE)
        self.help_category_footer = "\n"
        
        # Group all commands under Shell Commands
        self._cmd_to_category.update({
            'alias': 'Shell Commands',
            'connect_wifi': 'Shell Commands',
            'device_info': 'Shell Commands',
            'edit': 'Shell Commands',
            'execute_plugin': 'Shell Commands',
            'exec': 'Shell Commands',
            'exit': 'Shell Commands',
            'exploit': 'Shell Commands',
            'help': 'Shell Commands',
            'history': 'Shell Commands',
            'list_device_drivers': 'Shell Commands',
            'list_devices': 'Shell Commands',
            'list_plugins': 'Shell Commands',
            'list_targets': 'Shell Commands',
            'ls': 'Shell Commands',
            'lsdev': 'Shell Commands',
            'lsdrv': 'Shell Commands',
            'lsp': 'Shell Commands',
            'lst': 'Shell Commands',
            'lsusb': 'Shell Commands',
            'macro': 'Shell Commands',
            'quit': 'Shell Commands',
            'run_pyscript': 'Shell Commands',
            'run_script': 'Shell Commands',
            'runserver': 'Shell Commands',
            'set': 'Shell Commands',
            'set_log_format': 'Shell Commands',
            'set_log_level': 'Shell Commands',
            'shell': 'Shell Commands',
            'shortcuts': 'Shell Commands',
            'slf': 'Shell Commands',
            'sll': 'Shell Commands',
            'stop_server': 'Shell Commands',
        })

        # -- Command palette initialization (TTY-only) --------------------- #
        # The palette uses prompt-toolkit for live command discovery.
        # It is only initialized when stdin/stdout are TTYs so that non-interactive
        # use (pipes, scripts, tests) bypasses it entirely.
        self._palette_session = None
        self._canonical_command_registry = True
        if (
            _PALETTE_AVAILABLE
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        ):
            try:
                catalog = CommandCatalog(self)
                adapter = Cmd2CompletionAdapter(self)
                completer = CommandPaletteCompleter(self, catalog, adapter)
                self._palette_session = PaletteInputSession(self, completer)
            except Exception:
                self._palette_session = None

    def read_input(
        self,
        prompt: str,
        *,
        history=None,
        completion_mode=cmd2.utils.CompletionMode.NONE,
        preserve_quotes=False,
        choices=None,
        choices_provider=None,
        completer=None,
        parser=None,
    ) -> str:
        """Override cmd2's ``read_input`` to use the palette for top-level prompts.

        Only intercepts when:
        * ``completion_mode`` is ``COMMANDS`` (the top-level interactive prompt)
        * stdin and stdout are TTYs
        * ``use_rawinput`` is True
        * the palette session was successfully initialized
        * we are not at a continuation prompt

        Everything else delegates to ``super().read_input()`` unchanged.
        """
        if (
            completion_mode == cmd2.utils.CompletionMode.COMMANDS
            and self._palette_session is not None
            and not getattr(self, "_at_continuation_prompt", False)
            and sys.stdin.isatty()
            and sys.stdout.isatty()
            and self.use_rawinput
        ):
            try:
                return self._palette_session.prompt(prompt)
            except (KeyboardInterrupt, EOFError):
                raise
            except Exception:
                # Safe fallback: use cmd2's default input on any unexpected error
                pass

        return super().read_input(
            prompt,
            history=history,
            completion_mode=completion_mode,
            preserve_quotes=preserve_quotes,
            choices=choices,
            choices_provider=choices_provider,
            completer=completer,
            parser=parser,
        )

    def emptyline(self):
        self.onecmd("help")

    def do_quit(self, arg):
        """Deprecated alias for exit which preserves cleanup behavior."""
        return self.do_exit(arg)

    def precmd(self, statement):
        """Warn when an executable compatibility command is used directly."""
        statement = super().precmd(statement)
        replacement = LEGACY_REPLACEMENTS.get(statement.command)
        if replacement:
            self.pwarning(
                f"'{statement.command}' is deprecated; use '{replacement}'."
            )
        return statement

    def do_help(self, arg):
        'List available commands with "help" or detailed help with "help cmd".'
        requested = str(arg).strip()
        if requested and requested != "--all":
            # Show help for specific command
            super().do_help(requested)
            return

        self.poutput(ansi.style("\nIoTSploit Commands", fg=ansi.Fg.GREEN, bold=True))
        self.poutput("Use 'help <resource>' for actions and arguments.\n")
        width = max(len(resource.name) for resource in RESOURCE_SPECS) + 2
        for resource in RESOURCE_SPECS:
            self.poutput(
                ansi.style(f"  {resource.name:<{width}}", fg=ansi.Fg.CYAN)
                + resource.summary
            )

        self.poutput(ansi.style("\nShell Commands", fg=ansi.Fg.GREEN, bold=True))
        for name, summary in ESSENTIAL_COMMANDS:
            self.poutput(ansi.style(f"  {name:<11}", fg=ansi.Fg.CYAN) + summary)

        if requested == "--all":
            self.poutput(ansi.style("\nAdvanced cmd2 Commands", fg=ansi.Fg.GREEN, bold=True))
            self.poutput("  " + ", ".join(ADVANCED_COMMANDS))
            self.poutput(ansi.style("\nDeprecated Compatibility Commands", fg=ansi.Fg.YELLOW, bold=True))
            for legacy, replacement in sorted(LEGACY_REPLACEMENTS.items()):
                self.poutput(f"  {legacy:<24} -> {replacement}")
        else:
            self.poutput("\nUse 'help --all' to show advanced and deprecated commands.")

    def get_command_doc(self, cmd_name):
        """Get the first line of the command's docstring."""
        cmd_func = getattr(self, 'do_' + cmd_name, None)
        if cmd_func and cmd_func.__doc__:
            return cmd_func.__doc__.split('\n')[0]
        return ''

    def get_all_commands_by_category(self):
        """Return a dict mapping category names to lists of command names."""
        categories = {}
        
        # Get all command names (methods starting with 'do_')
        command_names = [attr[3:] for attr in dir(self) if attr.startswith('do_')]
        
        for cmd_name in command_names:
            # Get the command function
            cmd_func = getattr(self, 'do_' + cmd_name)
            
            # Get category from cmd2's category decorator or from our manual mapping
            if hasattr(cmd_func, 'category'):
                category = cmd_func.category
            else:
                # Check our manual mapping or default to 'Uncategorized'
                category = self._cmd_to_category.get(cmd_name, 'Uncategorized')
            
            # Add command to appropriate category list
            if category not in categories:
                categories[category] = []
            categories[category].append(cmd_name)
        
        return categories

    def _select_device(self, selected_plugin=None):
        """Helper method to handle device selection process"""
        try:
            available_plugins = [
                driver_name for driver_name, device 
                in self.connected_devices.items()
            ]
            
            if not available_plugins:
                logger.error(ansi.style("No initialized devices available", fg=ansi.Fg.RED))
                return False

            if selected_plugin:
                if selected_plugin not in available_plugins:
                    logger.error(
                        ansi.style(
                            f"Device '{selected_plugin}' is not initialized. "
                            f"Available devices: {', '.join(available_plugins)}",
                            fg=ansi.Fg.RED,
                        )
                    )
                    return False
            else:
                selected_plugin = Input_Mgr.Instance().single_choice(
                    "Select device plugin",
                    available_plugins
                )

            device = self.connected_devices.get(selected_plugin)
            if not device:
                logger.error(ansi.style(f"Device not found for {selected_plugin}", fg=ansi.Fg.RED))
                return False

            self._current_device = device
            self._current_driver = self.device_driver_manager.get_driver_instance(selected_plugin)
            self._current_plugin = selected_plugin

            logger.info(ansi.style(f"Selected device: {device.name}", fg=ansi.Fg.GREEN))
            return True

        except Exception as e:
            logger.error(ansi.style(f"Error during device selection: {str(e)}", fg=ansi.Fg.RED))
            logger.debug("Detailed error:", exc_info=True)
            return False

    def _display_devices(self, devices: Dict, sources: Dict):
        """Helper method to display device information"""
        for device_id, device in devices.items():
            source = sources.get(device_id, "unknown")
            source_color = ansi.Fg.GREEN if source == "dynamic" else ansi.Fg.BLUE
            
            logger.info(ansi.style(f"\n  Device ID: {device_id}", fg=ansi.Fg.CYAN))
            logger.info(ansi.style(f"  Source: {source}", fg=source_color))
            logger.info(f"  Name: {device.name}")
            logger.info("  " + "-" * 40)

    def _auto_initialize_devices(self):
        """自动扫描并初始化所有可用设备"""
        logger.info("Automatic device initialization started...")
        
        available_drivers = list(self.device_driver_manager.drivers.keys())
        if not available_drivers:
            logger.warning("No device drivers available!")
            return

        logger.info(f"Found {len(available_drivers)} drivers: {', '.join(available_drivers)}")

        for driver_name in available_drivers:
            try:
                logger.info(f"Initializing {driver_name}...")
                
                scan_result = self.device_driver_manager.scan_devices(driver_name)
                if scan_result['status'] != 'success':
                    logger.error(f"Failed to scan {driver_name}: {scan_result.get('message', 'Unknown error')}")
                    continue
                
                devices = scan_result.get('devices', [])
                if not devices:
                    logger.warning(f"No devices found for {driver_name}")
                    continue

                logger.info(f"Found {len(devices)} device(s) for {driver_name}")

                for device in devices:
                    try:
                        logger.info(f"Processing device: {device.name} (ID: {device.device_id})")

                        init_result = self.device_driver_manager.initialize_device(driver_name, device)
                        if init_result['status'] != 'success':
                            logger.error(f"Failed to initialize {device.name}: {init_result['message']}")
                            continue

                        connect_result = self.device_driver_manager.connect_device(driver_name, device)
                        if connect_result['status'] != 'success':
                            logger.error(f"Failed to connect {device.name}: {connect_result['message']}")
                            continue

                        self.connected_devices[driver_name] = device
                        logger.info(f"Successfully connected {device.name} using {driver_name}")

                    except Exception as e:
                        logger.error(f"Error processing device: {str(e)}")

            except Exception as e:
                logger.error(f"Error initializing {driver_name}: {str(e)}")

        self._show_initialization_summary()

    def _show_initialization_summary(self):
        """打印设备初始化摘要"""
        logger.info("Device Initialization Summary:")
        
        for driver_name, driver in self.device_driver_manager.drivers.items():
            logger.info("")
            logger.info(f"{driver_name}:")
            
            current_device = self.connected_devices.get(driver_name)
            
            if current_device:
                state = self.device_driver_manager.get_device_state(
                    driver_name, 
                    device_id=current_device.device_id
                )
                logger.info(f"  Device: {current_device.name}")
                logger.info(f"  State: {state.value}")
            else:
                logger.info("  Device: No device connected")
                logger.info("  State: unknown")
                
            commands = self.device_driver_manager.get_supported_commands(driver_name)
            if commands:
                logger.info(f"  Commands: {', '.join(commands.keys())}")

    def _cleanup_devices(self):
        """清理所有设备连接"""
        if not self.connected_devices:
            return

        logger.info("Cleaning up device connections...")
        for driver_name, device in list(self.connected_devices.items()):
            try:
                result = self.device_driver_manager.close_device(driver_name, device)
                if result['status'] == 'success':
                    logger.info(f"Successfully closed {device.name}")
                    del self.connected_devices[driver_name]
                else:
                    logger.error(f"Failed to close {device.name}: {result['message']}")
            except Exception as e:
                logger.error(f"Error closing {device.name}: {str(e)}")

def main():
    import signal
    import atexit

    parser = argparse.ArgumentParser(description='SAT Shell entrypoint')
    parser.add_argument('--runserver', action='store_true', help='Start servers directly and keep running until Ctrl+C; on Ctrl+C, stop servers')
    parser.add_argument(
        '--log-format',
        choices=LOG_FORMAT_CHOICES,
        default=None,
        help='Set terminal log format. Overrides --plain-log and IOTSPLOIT_LOG_FORMAT.',
    )
    parser.add_argument(
        '--plain-log',
        action='store_true',
        help='Use message-only terminal logs unless --log-format is also provided.',
    )
    args = parser.parse_args()

    selected_log_format = (
        args.log_format
        or ("plain" if args.plain_log else None)
        or os.getenv("IOTSPLOIT_LOG_FORMAT", "standard").strip().lower()
    )
    if selected_log_format not in LOG_FORMAT_CHOICES:
        selected_log_format = "standard"
    iots_logger.set_format(selected_log_format)
    logger.set_format(selected_log_format)

    shell = SAT_Shell()
    Report_Mgr.Instance().log_init()
    Env_Mgr.Instance().set("SAT_RUN_IN_SHELL", True)

    # Register OS signal + atexit handlers in the entrypoint so that unexpected exits
    # (terminal closed / SIGTERM) also trigger the same cleanup path.
    def _shutdown():
        try:
            shell.do_stop_server("")
        finally:
            try:
                shell._cleanup_devices()
            except Exception:
                pass

    def _signal_handler(signum, frame):  # noqa: ARG001
        _shutdown()
        raise SystemExit(0)

    def _atexit_handler():
        # Do not raise here; just best-effort cleanup.
        _shutdown()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)
    atexit.register(_atexit_handler)

    if args.runserver:
        ok = shell.do_runserver("")
        if ok is False:
            sys.exit(1)
        while True:
            time.sleep(1)
    else:
        shell.cmdloop()


if __name__ == '__main__':
    main()
