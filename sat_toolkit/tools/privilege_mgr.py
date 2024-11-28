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
        return os.geteuid() == 0

    def acquire_root_access(self):
        """Attempt to acquire root privileges using elevate"""
        if self.check_root_access():
            self.has_sudo_access = True
            return True

        try:
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