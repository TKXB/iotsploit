#!/usr/bin/env python
import os
import sys
import time
import importlib
import inspect
import argparse

LOG_FORMAT_CHOICES = ("standard", "compact", "plain")


def _tolerate_unencodable_output() -> None:
    """Never let a status message kill the process.

    The CLI prints emoji in its progress output. A Windows console on a
    non-UTF-8 code page (GBK on a Chinese install) raises UnicodeEncodeError
    on the first one, which killed the process during database setup -- before
    it could report what it was doing. Replacing the character is the right
    trade: the console cannot render it either way, and the run continues.

    Left alone where the stream already encodes them, so Linux output is
    unchanged.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass  # not a reconfigurable text stream (redirected, wrapped)


_tolerate_unencodable_output()


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

def ensure_database_migrated():
    """Apply pending migrations so an existing database follows the code.

    An existing database is copied first, so a failed migration can be undone
    by restoring the copy.
    """
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    import shutil

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plan:
        return
    names = ", ".join(f"{migration.app_label}.{migration.name}" for migration, _ in plan)
    print(f"📋 Applying database migrations: {names}")
    database = connection.settings_dict["NAME"]
    if executor.loader.applied_migrations and os.path.isfile(database):
        backup = f"{database}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(database, backup)
        print(f"💾 Database backed up to {backup}")
    call_command("migrate", interactive=False, verbosity=0)
    print("✅ Database migrations applied")


ensure_database_migrated()

# Now it's safe to import Django and other modules
import cmd2
from cmd2 import ansi
from iotsploit_cli.command_registry import (
    ADVANCED_COMMANDS,
    ESSENTIAL_COMMANDS,
    LEGACY_REPLACEMENTS,
    RESOURCE_SPECS,
)
from iotsploit_cli.commands.resource_commands import add_service_start_arguments, service_start_kwargs

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
from iotsploit_django.composition_root.wiring import get_exploit_plugin_manager
from iotsploit_django.tools.env_mgr import Env_Mgr
from iotsploit_django.tools.report_mgr import Report_Mgr
from iotsploit_django.tools.xlogger import xlog as logger
from iotsploit_core.core.interaction_binding import bind_interaction
from iotsploit_cli.interaction_console import ConsoleInteractionAdapter
from iotsploit_cli.plugin_log_console import console_plugin_logs
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
            if module_name == "linux_commands" and not sys.platform.startswith("linux"):
                continue
            
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
    
    logger.debug(f"Auto-discovered {len(command_classes)} command modules")
    return command_classes

# Auto-discover command modules
try:
    CommandMixins = discover_command_modules()
    logger.debug(f"Successfully loaded command modules: {[cls.__name__ for cls in CommandMixins]}")
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
        super().__init__()

        self.django_server_process = None
        self.daphne_server_process = None
        self.mcp_bridge_process = None
        self.celery_worker_process = None
        self.interactive_worker_process = None
        self.streaming_worker_process = None
        
        # The Django composition root selects the runner for this runtime.
        self.plugin_manager = get_exploit_plugin_manager()
        self.plugin_manager.initialize()
        
        # Initialize target manager
        self.target_manager = TargetManager.get_instance()
        self.target_manager.register_target("vehicle", Vehicle)
        
        # Check if database has any targets, if not, hint how to add one.
        existing_targets = self.target_manager.get_all_targets()
        if not existing_targets:
            logger.debug("No targets in database; use 'target import' or the UI to add one.")
        else:
            logger.debug(f"Found {len(existing_targets)} targets in database")
        
        # Note: Removed automatic JSON loading to prevent overwriting user changes
        # Use 'target_import conf/target.json' command if you need to import from JSON

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

    def onecmd_plus_hooks(self, *args, **kwargs):
        """Run every shell command with an operator attached to the terminal.

        A plugin can ask a question at any point during a run, and in the shell
        there is always someone there to answer it. Binding here rather than at
        each call site means every path that ends up executing a plugin --
        `exec`, plugin groups, sequences, run-all, and anything added later --
        can prompt without being wired up individually.

        The binding does not reach a plugin that prompts from a thread it
        spawned itself; context variables do not cross threads.

        A plugin's own log records are shown here for the same reason and over
        the same span: asking a question is only half a conversation, and
        without this the shell answered every one of them into a logger with no
        handler. Unlike the binding, this one does reach the threads a plugin
        spawns -- logging is process-global, which is why it is scoped to a
        single command rather than left on.
        """
        with bind_interaction(ConsoleInteractionAdapter()), console_plugin_logs():
            return super().onecmd_plus_hooks(*args, **kwargs)

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

def main():
    import signal
    import atexit

    parser = argparse.ArgumentParser(description='SAT Shell entrypoint')
    parser.add_argument('--runserver', action='store_true', help='Start servers directly and keep running until Ctrl+C; on Ctrl+C, stop servers')
    add_service_start_arguments(parser)
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
        shell.do_stop_server("")

    def _signal_handler(signum, frame):  # noqa: ARG001
        _shutdown()
        raise SystemExit(0)

    def _atexit_handler():
        # Do not raise here; just best-effort cleanup.
        _shutdown()

    for signal_name in ("SIGTERM", "SIGINT", "SIGHUP"):
        if shutdown_signal := getattr(signal, signal_name, None):
            signal.signal(shutdown_signal, _signal_handler)
    atexit.register(_atexit_handler)

    if args.runserver:
        ok = shell._start_services(**service_start_kwargs(args))
        if ok is False:
            sys.exit(1)
        while True:
            time.sleep(1)
    else:
        shell.cmdloop()


if __name__ == '__main__':
    main()
