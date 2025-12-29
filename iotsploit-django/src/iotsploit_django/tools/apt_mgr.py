import subprocess
import logging

logger = logging.getLogger(__name__)

class AptMgr:
    @staticmethod
    def is_package_installed(package_name: str) -> bool:
        """Check if a package is installed."""
        try:
            result = subprocess.run(
                ["dpkg", "-s", package_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8"
            )
            return "Status: install ok installed" in result.stdout
        except Exception as e:
            logger.error(f"Error checking package {package_name}: {e}")
            return False

    @staticmethod
    def install_package(package_name: str) -> bool:
        """Install a package using apt."""
        if AptMgr.is_package_installed(package_name):
            logger.info(f"Package {package_name} is already installed.")
            return True

        try:
            logger.info(f"Installing package {package_name}...")
            result = subprocess.run(
                ["sudo", "apt-get", "install", "-y", package_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8"
            )
            if result.returncode == 0:
                logger.info(f"Package {package_name} installed successfully.")
                return True
            else:
                logger.error(f"Failed to install package {package_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error installing package {package_name}: {e}")
            return False

    @staticmethod
    def remove_package(package_name: str) -> bool:
        """Remove a package using apt."""
        if not AptMgr.is_package_installed(package_name):
            logger.info(f"Package {package_name} is not installed.")
            return True

        try:
            logger.info(f"Removing package {package_name}...")
            result = subprocess.run(
                ["sudo", "apt-get", "remove", "-y", package_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8"
            )
            if result.returncode == 0:
                logger.info(f"Package {package_name} removed successfully.")
                return True
            else:
                logger.error(f"Failed to remove package {package_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error removing package {package_name}: {e}")
            return False

# Example usage:
# if not AptMgr.is_package_installed("some-package"):
#     AptMgr.install_package("some-package") 