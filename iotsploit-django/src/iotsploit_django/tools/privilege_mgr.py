import os
import logging
import elevate
from functools import wraps
import pwd
import grp

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
        requested plugin, stores the result in Redis, and exits.

        Args:
            plugin_name:  Name of the plugin (e.g. ``syn_flood_attack``)
            target:       Target dict to pass to the plugin (optional)
            parameters:   Parameter dict for the plugin (optional)
            python_executable: Path to the Python interpreter (defaults to
                              ``sys.executable`` - the same Python running Django).
                              Override if you need a specific Python path.

        Returns:
            (success, result_json) where *result_json* is the JSON result from Redis.
            *success* is *True* when the subprocess exited with return-code 0 and
            the result was successfully retrieved from Redis.
        """

        import subprocess, json, shlex, os, sys, uuid, time
        import redis
        from django.conf import settings

        # Generate a unique task ID for this execution
        task_id = str(uuid.uuid4())
        logger.info(f"Generated task ID: {task_id}")
        
        # Connect to Redis using Django settings
        redis_client = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            db=getattr(settings, 'REDIS_DB', 0)
        )
        
        # Check if task ID already exists in Redis (should not happen)
        result_key = f"plugin_result:{task_id}"
        existing_data = redis_client.get(result_key)
        if existing_data:
            logger.warning(f"Task ID collision! Key {result_key} already exists with data: {existing_data.decode('utf-8')[:100]}...")
        else:
            logger.debug(f"Task ID is unique, no existing data for key: {result_key}")

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

        logger.debug(f"Environment variables being passed:")
        logger.debug(f"  TASK_ID={task_id}")
        logger.debug(f"  TARGET_JSON={target_json[:100]}{'...' if len(target_json) > 100 else ''}")
        logger.debug(f"  PARAMS_JSON={params_json[:100]}{'...' if len(params_json) > 100 else ''}")

        # Create environment dict for subprocess
        env = os.environ.copy()
        env['TASK_ID'] = task_id
        env['TARGET_JSON'] = target_json
        env['PARAMS_JSON'] = params_json

        sudo_cmd = [
            "sudo", "-E",  # preserve environment so DJANGO_SETTINGS_MODULE etc. are inherited
            python_executable, "-m", runner_module, plugin_name
        ]

        logger.info("Executing plugin with sudo (task_id=%s): %s", task_id, " ".join(sudo_cmd))

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
            logger.info(f"Subprocess completed in {execution_time:.2f} seconds (task_id={task_id})")
            
            # Log subprocess output for debugging
            if proc.stdout:
                logger.info(f"Subprocess stdout (task_id={task_id}): {proc.stdout[:500]}{'...' if len(proc.stdout) > 500 else ''}")
            else:
                logger.debug(f"Subprocess stdout is empty (task_id={task_id})")
                
            if proc.stderr:
                logger.info(f"Subprocess stderr (task_id={task_id}): {proc.stderr[:500]}{'...' if len(proc.stderr) > 500 else ''}")
            else:
                logger.debug(f"Subprocess stderr is empty (task_id={task_id})")

            if proc.returncode != 0:
                logger.error("sudo subprocess failed (rc=%s): stderr='%s', stdout='%s'", 
                           proc.returncode, proc.stderr.strip(), proc.stdout.strip())
                return False, proc.stderr.strip() or proc.stdout.strip()

            # Subprocess completed successfully, retrieve result from Redis
            result_key = f"plugin_result:{task_id}"
            logger.info(f"Subprocess completed successfully, retrieving result from Redis key: {result_key}")
            
            result_data = redis_client.get(result_key)
            if result_data:
                # Clean up the Redis key
                redis_client.delete(result_key)
                decoded_result = result_data.decode('utf-8')
                logger.info(f"Retrieved result from Redis (task_id={task_id}): {decoded_result[:200]}...")
                return True, decoded_result
            else:
                logger.error("No result found in Redis for task_id=%s", task_id)
                return False, f"No result found in Redis (task_id: {task_id})"

        except subprocess.TimeoutExpired:
            logger.error("sudo subprocess timed out")
            return False, "Plugin execution timed out"
        except FileNotFoundError as e:
            logger.error("Failed to execute sudo or python: %s", e)
            return False, str(e)
        except Exception as e:
            logger.exception("Unexpected error running plugin with sudo")
            return False, str(e)

