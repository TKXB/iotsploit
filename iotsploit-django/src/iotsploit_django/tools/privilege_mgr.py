import os
import logging
import elevate
from functools import wraps

logger = logging.getLogger(__name__)

class PrivilegeManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.has_sudo_access = False

    @staticmethod
    def requires_root(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            priv_mgr = PrivilegeManager()
            if not priv_mgr.check_root_access():
                if not priv_mgr.acquire_root_access():
                    raise PermissionError("Root privileges required but couldn't be acquired")
            return func(self, *args, **kwargs)
        return wrapper

    def check_root_access(self):
        """Check if we currently have root privileges"""
        logger.info("Checking root access")
        is_root = os.geteuid() == 0
        logger.info(f"Checking root access. Current euid: {os.geteuid()}, is_root: {is_root}")
        return is_root

    def acquire_root_access(self):
        """Attempt to acquire root privileges using elevate"""
        if self.check_root_access():
            self.has_sudo_access = True
            return True

        try:
            logger.info("Attempting to elevate privileges. The application will restart...")
            logger.info("Please rerun your command after the restart completes.")
            # Use elevate to get root privileges
            elevate.elevate(graphical=False)
            
            if self.check_root_access():
                self.has_sudo_access = True
                logger.info("Successfully acquired root privileges")
                return True
            else:
                logger.error("Failed to acquire root privileges")
                return False

        except Exception as e:
            logger.error(f"Error acquiring root privileges: {str(e)}")
            return False

    def run_with_privilege(self, command):
        """Run a command with root privileges"""
        if not self.has_sudo_access and not self.acquire_root_access():
            raise PermissionError("Unable to acquire root privileges")

        try:
            import subprocess
            process = subprocess.run(command, capture_output=True, text=True)
            return process.returncode == 0, process.stdout, process.stderr

        except Exception as e:
            logger.error(f"Error running privileged command: {str(e)}")
            raise



    # ------------------------------------------------------------------
    # Django-friendly helper: execute plugin in a separate sudo process
    # ------------------------------------------------------------------
    def run_plugin_with_sudo(self, plugin_name: str, target: dict | None = None,
                             parameters: dict | None = None, python_executable: str = None) -> tuple[bool, str]:
        """Run a SAT exploit plugin with root privileges via *sudo*.

        This helper is designed for web servers (e.g. Django) where in-process
        privilege escalation is undesired or impossible.  It launches a new
        subprocess under *sudo* that imports the SAT toolkit, executes the
        requested plugin, writes the result to a private result file, and exits.

        Args:
            plugin_name:  Name of the plugin (e.g. ``syn_flood_attack``)
            target:       Target dict to pass to the plugin (optional)
            parameters:   Parameter dict for the plugin (optional)
            python_executable: Path to the Python interpreter (defaults to
                              ``sys.executable`` - the same Python running Django).
                              Override if you need a specific Python path.

        Returns:
            (success, result_json) where *result_json* is the JSON result document.
            *success* is *True* when the subprocess exited with return-code 0 and
            the result file contained valid JSON.
        """

        import subprocess
        import json
        import os
        import sys
        import tempfile
        import time

        target_json = json.dumps(target or {})
        params_json = json.dumps(parameters or {})
        
        logger.debug(f"Serialized target_json: {target_json}")
        logger.debug(f"Serialized params_json: {params_json}")

        # The helper runner lives inside iotsploit_django.tools
        runner_module = "iotsploit_django.tools.plugin_sudo_runner"

        # Auto-detect the correct Python executable if not provided
        if python_executable is None:
            # Use the same Python executable that's currently running Django
            python_executable = sys.executable
            logger.info(f"Using Python executable: {python_executable}")

        logger.debug("Environment variables being passed:")
        logger.debug(f"  TARGET_JSON={target_json[:100]}{'...' if len(target_json) > 100 else ''}")
        logger.debug(f"  PARAMS_JSON={params_json[:100]}{'...' if len(params_json) > 100 else ''}")

        result_file = tempfile.NamedTemporaryFile(prefix="iotsploit-result-", suffix=".json", delete=False)
        result_path = result_file.name
        result_file.close()

        env = os.environ.copy()
        env['RESULT_PATH'] = result_path
        env['TARGET_JSON'] = target_json
        env['PARAMS_JSON'] = params_json

        sudo_cmd = [
            "sudo", "-E",  # preserve environment so DJANGO_SETTINGS_MODULE etc. are inherited
            python_executable, "-m", runner_module, plugin_name
        ]

        logger.info("Executing plugin with sudo: %s", " ".join(sudo_cmd))

        try:
            # Start the subprocess
            start_time = time.time()
            logger.debug(f"Starting subprocess at {start_time}")
            
            proc = subprocess.run(
                sudo_cmd,
                capture_output=True,
                text=True,
                check=False,
                env=env  # Pass the environment variables
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            logger.info(f"Subprocess completed in {execution_time:.2f} seconds")
            
            # Log subprocess output for debugging
            if proc.stdout:
                logger.info(f"Subprocess stdout: {proc.stdout[:500]}{'...' if len(proc.stdout) > 500 else ''}")
            else:
                logger.debug("Subprocess stdout is empty")
                
            if proc.stderr:
                logger.info(f"Subprocess stderr: {proc.stderr[:500]}{'...' if len(proc.stderr) > 500 else ''}")
            else:
                logger.debug("Subprocess stderr is empty")

            if proc.returncode != 0:
                logger.error("sudo subprocess failed (rc=%s): stderr='%s', stdout='%s'", 
                           proc.returncode, proc.stderr.strip(), proc.stdout.strip())
                return False, proc.stderr.strip() or proc.stdout.strip()

            try:
                with open(result_path, encoding="utf-8") as result_handle:
                    result_data = result_handle.read()
                json.loads(result_data)
            except (OSError, json.JSONDecodeError) as exc:
                detail = proc.stderr.strip()
                logger.error("Invalid privileged result file: %s", exc)
                return False, f"Invalid privileged result: {exc}{': ' + detail if detail else ''}"
            return True, result_data

        except subprocess.TimeoutExpired:
            logger.error("sudo subprocess timed out")
            return False, "Plugin execution timed out"
        except FileNotFoundError as e:
            logger.error("Failed to execute sudo or python: %s", e)
            return False, str(e)
        except Exception as e:
            logger.exception("Unexpected error running plugin with sudo")
            return False, str(e)
        finally:
            try:
                os.unlink(result_path)
            except FileNotFoundError:
                pass
