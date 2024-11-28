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

    def drop_privileges(self):
        """Drop root privileges and return to normal user"""
        try:
            # Get SUDO_USER from environment, fall back to LOGNAME or USER if not running with sudo
            username = os.environ.get('SUDO_USER') or os.environ.get('LOGNAME') or os.environ.get('USER')
            logger.info(f"Username: {username}")
            if not username:
                raise RuntimeError("Could not determine the original user")

            # Get the uid/gid from the name
            pw_record = pwd.getpwnam(username)
            uid = pw_record.pw_uid
            gid = pw_record.pw_gid

            # Init group access list
            os.initgroups(username, gid)

            # Drop privileges
            os.setgid(gid)
            os.setuid(uid)

            # Ensure a very conservative umask
            os.umask(0o077)

            # Verify privileges were dropped
            if os.getuid() != uid or os.geteuid() != uid:
                raise RuntimeError("Failed to drop privileges")

            logger.info(f"Successfully dropped root privileges to user: {username}")

        except Exception as e:
            logger.error(f"Error dropping privileges: {str(e)}")
            raise RuntimeError("Failed to drop privileges") from e

