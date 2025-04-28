import logging
logger = logging.getLogger(__name__)

import os
import re
import threading
from sat_toolkit.tools.usb_mgr import USB_Mgr
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from sat_toolkit.models.Target_Model import TargetManager, ADBDevice

from pwnlib import term
term.term_mode = True
from pwn import *
from pwnlib.exception import PwnlibException


class ADB_Mgr:
    """
    ADB Manager for interacting with Android devices.
    
    Usage with target model:
    1. Define ADB devices in the target JSON:
       - Use 'dhu', 'tcam', or 'adb_device' as the component type
       - Specify adb_serial_id, usb_vendor_id, and usb_product_id fields
       - Example:
         {
           "component_id": "comp_dhu_001",
           "name": "DHU",
           "type": "dhu",
           "status": "active",
           "adb_serial_id": "DEVICE_SERIAL_ID",
           "usb_vendor_id": "0x18d1",
           "usb_product_id": "0x4ee7"
         }
    
    2. Access devices by name or type:
       - Use the device name (e.g., "DHU", "TCAM")
       - Or device type (e.g., "dhu", "tcam", "custom_adb_device")
       - Or direct serial id if known
    """
    
    # Device type identifiers - use these as names in the target json
    DHU_NAME = "DHU"
    TCAM_NAME = "TCAM"
    
    # Target property keys
    TARGET_DHU_SERIAL = "DHU_ADB_SERIAL_ID"
    TARGET_DHU_VENDOR_ID = "DHU_USB_VendorID"
    TARGET_DHU_PRODUCT_ID = "DHU_USB_ProductID"
    TARGET_TCAM_SERIAL = "TCAM_ADB_SERIAL_ID"
    TARGET_TCAM_VENDOR_ID = "TCAM_USB_VendorID"
    TARGET_TCAM_PRODUCT_ID = "TCAM_USB_ProductID"
    
    # File paths
    __temp_script_file_path = "/data/local/tmp/iotsploit/tmp_bash_script.sh"
    
    # Singleton pattern implementation
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ADB_Mgr, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    @staticmethod
    def Instance():
        return ADB_Mgr()
        
    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            logger.info("Initializing ADB_Mgr singleton")
            self.__last_connect_serial = None
            self.__last_adb_root = None
            self._target_manager = TargetManager.get_instance()
            self._initialized = True
        
    def init_adb_service(self):
        """ADB_mgr must be initialized in the main thread"""
        logger.info("Init ADB Services As Root")
        self.list_devices()

    def query_adb_serial_id(self, device_identifier):
        """
        Get ADB serial ID for any ADB device by name or type
        
        Args:
            device_identifier: Device name or type
            
        Returns:
            ADB serial ID string
        """
        current_target = self._target_manager.get_current_target()
        if not current_target:
            raise_err("No current target set. Cannot query ADB serial ID.")
        
        # First try by name (for backward compatibility with DHU_NAME/TCAM_NAME)
        adb_device = current_target.get_adb_device_by_name(device_identifier)
        
        # If not found by name, try by type
        if not adb_device:
            adb_device = current_target.get_adb_device_by_type(device_identifier)
            
        if adb_device and adb_device.adb_serial_id:
            logger.info(f"ADB device '{device_identifier}' serial ID found: {adb_device.adb_serial_id}")
            return adb_device.adb_serial_id
            
        # If we have USB IDs, use them to find the device
        if adb_device and adb_device.usb_vendor_id and adb_device.usb_product_id:
            logger.info(f"Using USB IDs to find ADB device '{device_identifier}'")
            return self._find_device_by_usb_ids(
                adb_device.usb_vendor_id, 
                adb_device.usb_product_id, 
                device_identifier
            )
            
        raise_err(f"ADB device '{device_identifier}' not found in target or missing required information")

    def _get_target_property(self, prop_name, default=None):
        """Get a property from the current target"""
        # Try to get from target
        current_target = self._target_manager.get_current_target()
        
        if current_target:
            # Check in export_for_adb first
            try:
                adb_info = current_target.export_for_adb()
                if prop_name in adb_info:
                    logger.debug(f"Found {prop_name} in target export_for_adb: {adb_info[prop_name]}")
                    return adb_info[prop_name]
            except:
                logger.debug(f"Error getting export_for_adb from target")
                
            # Check in target properties
            if prop_name in current_target.properties:
                logger.debug(f"Found {prop_name} in target properties: {current_target.properties[prop_name]}")
                return current_target.properties[prop_name]
                
            # Check in components (for future extensibility)
            if hasattr(current_target, 'components'):
                for component in current_target.components:
                    comp_props = component.properties
                    if prop_name in comp_props:
                        logger.debug(f"Found {prop_name} in component {component.name}: {comp_props[prop_name]}")
                        return comp_props[prop_name]
                    
            # Check for direct attributes
            if hasattr(current_target, prop_name):
                logger.debug(f"Found {prop_name} as direct attribute: {getattr(current_target, prop_name)}")
                return getattr(current_target, prop_name)
        
        logger.debug(f"Property {prop_name} not found in target, returning default: {default}")
        return default

    def query_dhu_adb_serial_id(self):
        """Get DHU device serial ID from target or by USB device"""
        current_target = self._target_manager.get_current_target()
        if not current_target:
            raise_err("No current target set. Cannot query DHU ADB serial ID.")
        
        # Get DHU from components
        dhu_device = current_target.get_adb_device_by_name(self.DHU_NAME)
        
        if dhu_device and dhu_device.adb_serial_id:
            logger.info(f"DHU ADB SERIAL ID Found: {dhu_device.adb_serial_id}")
            return dhu_device.adb_serial_id

        logger.info("DHU ADB SERIAL ID NOT Found! Use usb_vendor_id AND usb_product_id Instead")
        
        # Try to get vendor/product ID from DHU component
        if dhu_device and dhu_device.usb_vendor_id and dhu_device.usb_product_id:
            return self._find_device_by_usb_ids(dhu_device.usb_vendor_id, dhu_device.usb_product_id, "DHU")
        else:
            raise_err("DHU ADB Serial ID and USB IDs not configured in target")

    def query_tcam_adb_serial_id(self):
        """Get TCAM device serial ID from target or by USB device"""
        current_target = self._target_manager.get_current_target()
        if not current_target:
            raise_err("No current target set. Cannot query TCAM ADB serial ID.")
        
        # Get TCAM from components
        tcam_device = current_target.get_adb_device_by_name(self.TCAM_NAME)
        
        if tcam_device and tcam_device.adb_serial_id:
            logger.info(f"TCAM ADB SERIAL ID Found: {tcam_device.adb_serial_id}")
            return tcam_device.adb_serial_id
        
        logger.info("TCAM ADB SERIAL ID NOT Found! Use usb_vendor_id AND usb_product_id Instead")
        
        # Try to get vendor/product ID from TCAM component
        if tcam_device and tcam_device.usb_vendor_id and tcam_device.usb_product_id:
            return self._find_device_by_usb_ids(tcam_device.usb_vendor_id, tcam_device.usb_product_id, "TCAM")
        else:
            raise_err("TCAM ADB Serial ID and USB IDs not configured in target")

    def _find_device_by_usb_ids(self, vendor_id, product_id, device_name):
        """Find device serial by vendor ID and product ID"""
        for usb in USB_Mgr.Instance().list_usb_devices():
            if usb["idVendor"] == int(vendor_id, 16) and usb["idProduct"] == int(product_id, 16):
                logger.info(f"Find {device_name} USB In USB List: {usb}")
                return usb["iSerialNumber"]
            
        raise_err(f"{device_name} ADB Serial ID 查询失败! 连接的USB设备中没有找到匹配设备")

    def __recheck_device_serial(self, device_serial):
        """Resolve special device serial placeholders to actual values"""
        # For backwards compatibility
        if device_serial == self.DHU_NAME:
            device_serial = self.query_dhu_adb_serial_id()
        elif device_serial == self.TCAM_NAME:
            device_serial = self.query_tcam_adb_serial_id()
        # Try to resolve as an ADB device from the target model
        elif not (device_serial and re.match(r'[A-Za-z0-9.:]+$', device_serial)):
            try:
                device_serial = self.query_adb_serial_id(device_serial)
            except Exception as e:
                logger.debug(f"Could not find ADB device '{device_serial}': {str(e)}")
                # If not found as a name/type, keep as is - could be a direct serial

        if device_serial is None:
            raise_err(f"Device Serial: {device_serial} Invalid!")
        
        return device_serial

    def check_connect_status(self, device_serial):
        """Check if the device is connected via ADB"""
        if device_serial is None:
            raise_err("Device Serial Invalid!")

        # Find the actual device serial if a placeholder was provided
        device_serial_checked = None
        
        # For backwards compatibility
        if device_serial == self.DHU_NAME:
            try:
                device_serial_checked = self.query_dhu_adb_serial_id()
            except Exception:
                logger.info("DHU ADB device not found")
                return False
        elif device_serial == self.TCAM_NAME:
            try:
                device_serial_checked = self.query_tcam_adb_serial_id()
            except Exception:
                logger.info("TCAM ADB device not found")
                return False
        # General device lookup by name or type
        elif not re.match(r'[A-Za-z0-9.:]+$', device_serial):
            try:
                device_serial_checked = self.query_adb_serial_id(device_serial)
            except Exception:
                logger.info(f"ADB device '{device_serial}' not found")
                return False
        else:
            device_serial_checked = device_serial

        # Check if the device is in the ADB device list
        adb_devices = self.list_devices()
        for dev in adb_devices:
            if dev.serial == device_serial_checked:
                logger.info(f"Find Serial IN ADB: {dev}")
                return True
                
        logger.info(f"Serial: {device_serial_checked} Not Found IN ADB Devices")
        return False

    def list_devices(self):
        """
        Check ADB connection status
        
        Returns:
            List of ADB devices
        """
        try:
            device_list = adb.devices()
            logger.info(f"Curr ADB Devices Count: {len(device_list)}\n{device_list}")
            return device_list
        except PwnlibException as e:
            if "'./adb' does not exist" in str(e):
                logger.error("ADB not found. Please install ADB and add it to your PATH")
            else:
                logger.error(f"ADB connection error: {str(e)}")
            return []
        except Exception as err:
            logger.exception("ADB List Devices Fail!")
            return []

    def connect_dev(self, device_serial, root_require=False, force_unroot=False):
        """
        Connect to a device via ADB and optionally request root access
        
        Args:
            device_serial: Device serial ID or placeholder
            root_require: Whether root access is required
            force_unroot: Force non-root access even if previously rooted
            
        Returns:
            Device serial if connected successfully, None otherwise
        """
        device_serial_checked = self.__recheck_device_serial(device_serial)
        
        # Check if reconnection is needed
        need_reconnect = False
        if device_serial_checked != self.__last_connect_serial:
            need_reconnect = True
        if root_require and self.__last_adb_root is False:
            need_reconnect = True
        if not root_require and force_unroot and self.__last_adb_root:
            need_reconnect = True

        if not need_reconnect:
            logger.info(f"Current: {self.__last_connect_serial}_{self.__last_adb_root} "
                      f"Need: {device_serial_checked}_{root_require}_{force_unroot} "
                      f"Match requirements. Skip")
            return self.__last_connect_serial

        logger.info(f"Current: {self.__last_connect_serial}_{self.__last_adb_root} "
                  f"Need: {device_serial_checked}_{root_require}_{force_unroot} "
                  f"ADB Connect Start")

        # Reset connection state
        self.__last_connect_serial = None
        self.__last_adb_root = None

        try:
            # Find device in ADB device list
            device_list = self.list_devices()
            target_dev = None
            for dev in device_list:
                if dev.serial == device_serial_checked:
                    target_dev = dev
                    break
            
            if target_dev is None:
                logger.error(f"ADB Find Device Fail! Serial: {device_serial_checked} Not Found")
                return None

            # Connect to device
            context.device = device_serial_checked
            adb.wait_for_device()
            logger.info(f"ADB Connect Device Success: {target_dev}")
            
        except Exception as err:
            logger.exception("ADB Connect Device Fail! Connect Abort")
            return None  

        # Handle root requirements
        if root_require:
            logger.info("ADB Root Required.")
            if self.__last_adb_root is not True:
                try:
                    adb.root()
                    sat_sleep(2)
                    logger.info("ADB Root Required. Restart ADBD As Root.")
                    self.__last_adb_root = True
                except Exception as err:
                    logger.exception("ADB Root Fail! Connect Abort")
                    self.__last_adb_root = None
                    return None
            else:
                logger.info("ADB Already Rooted")
        else:
            if force_unroot:
                logger.info("ADB Force UnRoot Required.")
                if self.__last_adb_root is not False:
                    try:
                        adb.unroot() 
                        sat_sleep(2)
                        logger.info("ADB Root NOT Required. Restart ADBD As Shell.")
                        self.__last_adb_root = False
                    except Exception as err:
                        self.__last_adb_root = None
                        logger.exception("ADB UnRoot Request Fail! Connect Abort.")
                        return None
                else:
                    logger.info("ADB Already UnRooted")
            else:
                logger.info("ADB Force UnRoot NOT Required.")
                if self.__last_adb_root is None:
                    logger.info("Default ADB Treat As Shell.")
                    self.__last_adb_root = False
    
        self.__last_connect_serial = device_serial_checked
        return self.__last_connect_serial

    def pull_file(self, device_serial, android_file_path, sat_file_path):
        """
        Pull a file from an Android device
        
        Args:
            device_serial: Device serial ID or placeholder
            android_file_path: Path to file on Android device
            sat_file_path: Path to save file on host
            
        Returns:
            1: Success
            -1: Device connect fail
            -2: File pull fail
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")

        try:
            adb.pull(android_file_path, sat_file_path)
            logger.info(f"Device: {device_serial} Pull File {android_file_path} -> {sat_file_path} Success.")
            return 1
        except Exception as err:
            logger.exception(f"Device: {device_serial} Pull File {android_file_path} -> {sat_file_path} Fail!")
            return -2
    
    def push_file(self, device_serial, sat_file_path, android_file_path):
        """
        Push a file to an Android device
        
        Args:
            device_serial: Device serial ID or placeholder
            sat_file_path: Path to file on host
            android_file_path: Path to save file on Android device
            
        Returns:
            1: Success
            -1: Device connect fail
            -2: File push fail
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")

        try:
            adb.push(sat_file_path, android_file_path)
            logger.info(f"Device: {device_serial} Push File {sat_file_path} -> {android_file_path} Success.")
            return 1
        except Exception as err:
            logger.exception(f"Device: {device_serial} Push File {sat_file_path} -> {android_file_path} Fail!")
            return -2

    def list_installed_apps(self, device_serial):
        """
        List installed apps on an Android device
        
        Args:
            device_serial: Device serial ID or placeholder
            
        Returns:
            List of package names or None on failure
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")
        
        try:
            app_list = []
            packages = adb.process(['pm', 'list', 'packages']).recvall().decode('utf-8')
            for package_line in packages.splitlines():
                app_list.append(package_line.replace("package:", ""))
            logger.info(f"Device: {device_serial} List Installed APPs Success. APPs: {app_list}")
            return app_list
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} List Installed APPs Fail!")
            return None

    def query_dir_status(self, device_serial, dir_path):
        """
        Get directory listing details from an Android device
        
        Args:
            device_serial: Device serial ID or placeholder
            dir_path: Directory path to list
            
        Returns:
            List of directory contents (permissions, owner, name) or None on failure
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")
        
        try:
            result_list = []
            results = adb.process(['ls', '-l', dir_path]).recvall().decode('utf-8')
            if results.startswith("total "):
                for line in results.splitlines()[1:]:
                    # Split by whitespace but handle multiword filenames
                    parts = line.split()
                    if len(parts) >= 8:
                        item_dict = {
                            "type": parts[0],
                            "owner": f"{parts[2]}:{parts[3]}",
                            "name": parts[-1]
                        }
                        result_list.append(item_dict)

                logger.info(f"Device: {device_serial} List Query Dir: {dir_path} Success. Dir Status: {result_list}")
                return result_list
            else:
                logger.info(f"Device: {device_serial} List Query Dir: {dir_path} Fail! Dir Not Exists.")
                return []
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} List Query Dir: {dir_path} Fail! ADB Cmd Fail!")
            return None

    def shell_cmd(self, device_serial, cmd, root_required=True):
        """
        Execute a shell command on an Android device
        
        Args:
            device_serial: Device serial ID or placeholder
            cmd: Shell command to execute
            root_required: Whether root access is required
            
        Returns:
            Command output as string
        """
        if root_required:
            con_dev = self.connect_dev(device_serial, True)
        else:
            con_dev = self.connect_dev(device_serial, False)
            
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")

        logger.info(f"Device: {device_serial} Execute Shell CMD: {cmd} Start -->>")
        
        # Create temp script file
        adb.makedirs(os.path.dirname(self.__temp_script_file_path))
        adb.write(self.__temp_script_file_path, cmd)
        
        # Execute command
        results = adb.process(["sh", self.__temp_script_file_path]).recvall().decode('utf-8')
        logger.info(f"Device: {device_serial} Execute Shell CMD: {cmd} Finish -->>")

        return results

    def _filter_file_items(self, items, passdirs, passsids, hasSelinux, allowdirs=None, is_dir=False):
        """Helper function to filter file listings by path and SELinux context"""
        filtered_items = []
        for item in items:
            # Add trailing slash to directories for consistent path handling
            path = item["filepath"]
            if is_dir:
                path = path + "/"
                item["dirpath"] = path
                del item["filepath"]
                
            # Filter by path prefixes (exclude virtual directories)
            if any(path.startswith(excluded) for excluded in passdirs):
                continue
                
            # Filter by mount points
            if allowdirs:
                if not any(path.startswith(allowed) for allowed in allowdirs):
                    continue
                    
            # Filter by SELinux context
            if hasSelinux and any(passsid in item["sid"] for passsid in passsids):
                continue
                
            filtered_items.append(item)
            
        return filtered_items

    def query_writable_mount_dirs(self, device_serial):
        """Get list of writable mount points on device"""
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")

        try:
            cmd = ("mount | grep rw | grep -v function | grep -v tmpfs | grep -v bpf | "
                   "grep -v binder | grep -v configfs | grep -v tracefs | "
                   "grep -v cgroup | grep -v selinuxfs | grep -v proc | grep -v devpts | grep -v sysfs")
            results = self.shell_cmd(device_serial, cmd)
            
            # Extract mount points
            dirs = []
            itemre = re.compile(r"on\s+(\S+)")
            for line in results.splitlines():
                match = itemre.findall(line)
                if match:
                    dirs.append(match[0] + "/")
                    
            return dirs
        except Exception as err:
            logger.exception(f"Device: {device_serial} query mount Fail! ADB Cmd Fail!")
            return []

    def _parse_permission_listings(self, results):
        """Parse permissions listing output from ls -l -Z"""
        items = []
        itemregx = re.compile(r"(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
        for line in results.splitlines():
            match = itemregx.findall(line)
            if match:
                items.append({
                    "rwx": match[0][0],
                    "owner": match[0][1],
                    "group": match[0][2],
                    "sid": match[0][3],
                    "filepath": match[0][4]
                })
        return items

    def query_dirs_permission_writable_by_any_user(self, device_serial, finddir, namefilter="", passdirs=[], passsids=[]):
        """
        Find directories writable by any user
        
        Args:
            device_serial: Device serial ID or placeholder
            finddir: Directory to search in
            namefilter: Optional name pattern filter
            passdirs: Directories to exclude
            passsids: SELinux contexts to exclude
            
        Returns:
            List of writable directories with details
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")            

        try:
            # Build the find command
            if namefilter:
                cmd = f'find {finddir} -perm -2 -type d -name "{namefilter}" -print0 2>/dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null'
            else:
                cmd = f'find {finddir} -perm -2 -type d -print0 2>/dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null'
                
            results = self.shell_cmd(device_serial, cmd)
            
            # Parse and filter results
            hasSelinux = self.query_android_selinux_status(self.DHU_NAME)
            allowdirs = self.query_writable_mount_dirs(device_serial)
            items = self._parse_permission_listings(results)
            dirs = self._filter_file_items(items, passdirs, passsids, hasSelinux, allowdirs, True)
            
            logger.info(f"Device: {device_serial} Query Dirs Permissions Success.")
            return dirs
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} query_dirs_permission Fail! ADB Cmd Fail!")
            return None

    def query_files_permission_readable_by_any_user(self, device_serial, finddir, namefilter="", passdirs=[], passsids=[]):
        """
        Find files readable by any user
        
        Args:
            device_serial: Device serial ID or placeholder
            finddir: Directory to search in
            namefilter: Optional name pattern filter
            passdirs: Directories to exclude
            passsids: SELinux contexts to exclude
            
        Returns:
            List of readable files with details
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")     
            
        try:
            # Build the find command
            if namefilter:
                cmd = f'find {finddir} -perm -4 -type f -name "{namefilter}" -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null'
            else:
                cmd = f'find {finddir} -perm -4 -type f -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null'
                
            results = self.shell_cmd(device_serial, cmd)
            
            # Parse and filter results
            hasSelinux = self.query_android_selinux_status(self.DHU_NAME)
            items = self._parse_permission_listings(results)
            files = self._filter_file_items(items, passdirs, passsids, hasSelinux)
            
            return files
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} query_files_permission Fail! ADB Cmd Fail!")
            return None

    def query_files_permission_writable_by_any_user(self, device_serial, finddir, namefilter="", passdirs=[], passsids=[]):
        """
        Find files writable by any user
        
        Args:
            device_serial: Device serial ID or placeholder
            finddir: Directory to search in
            namefilter: Optional name pattern filter
            passdirs: Directories to exclude
            passsids: SELinux contexts to exclude
            
        Returns:
            List of writable files with details
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")     

        try:
            # Build the find command
            if namefilter:
                cmd = f'find {finddir} -perm -2 -type f -name "{namefilter}" -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null'
            else:
                cmd = f'find {finddir} -perm -2 -type f -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null'
                
            results = self.shell_cmd(device_serial, cmd)
            
            # Parse and filter results
            hasSelinux = self.query_android_selinux_status(self.DHU_NAME)
            allowdirs = self.query_writable_mount_dirs(device_serial)
            items = self._parse_permission_listings(results)
            files = self._filter_file_items(items, passdirs, passsids, hasSelinux, allowdirs)
            
            return files
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} query_files_permission Fail! ADB Cmd Fail!")
            return None
        
    def query_files_permission_suid(self, device_serial):
        """
        Find SUID files on the device
        
        Args:
            device_serial: Device serial ID or placeholder
            
        Returns:
            List of SUID files with details
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")     

        try:
            cmd = 'find / -perm -4000 -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null'
            results = self.shell_cmd(device_serial, cmd)
            
            # Just parse, no filtering
            items = self._parse_permission_listings(results)
            
            return items
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} Query SUID Files Permissions Fail! ADB Cmd Fail!")
            return None

    # TODO: Implement activity launching with specific user
    def start_activity_with_user(self, device_serial, activity_name, user):
        """Start an activity as a specific user (not implemented yet)"""
        logger.info("start_activity_with_user called! 功能尚未实现")
        return 1

    def install_apk(self, device_serial, apk_path):
        """
        Install an APK on the device
        
        Args:
            device_serial: Device serial ID or placeholder
            apk_path: Path to APK file
            
        Returns:
            True if installation was successful, False otherwise
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")
            
        try:
            real_device_serial = self.__recheck_device_serial(device_serial)
            _, result = Bash_Script_Mgr.Instance().exec_cmd(f"adb -s {real_device_serial} install {apk_path}")
            
            if "success" in result.lower():
                logger.info(f"Install APK Finish: {apk_path}")
                return True
            else:
                logger.warning(f"Install APK failed: {apk_path}. Result: {result}")
                return False
        except Exception as err:
            logger.exception(f"Device: {device_serial} Install APK Fail: {apk_path}")
            return False
    
    def uninstall_apk(self, device_serial, package_id):
        """
        Uninstall an app from the device
        
        Args:
            device_serial: Device serial ID or placeholder
            package_id: Package name to uninstall
            
        Returns:
            True if uninstallation was successful, False otherwise
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")
        
        try:
            adb.uninstall(package_id)
            logger.info(f"Device: {device_serial} UnInstall Package Finish: {package_id}")
            return True
        except Exception as err:
            logger.exception(f"Device: {device_serial} UnInstall Package Fail: {package_id}")
            return False

    def query_android_selinux_status(self, device_serial):
        """
        Check SELinux status on the device
        
        Args:
            device_serial: Device serial ID or placeholder
            
        Returns:
            True if SELinux is enforcing, False if permissive/disabled, None on error
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")    

        try:
            selinux_status = adb.process(['getenforce']).recvall().decode('utf-8').strip()
            logger.info(f"Device: {device_serial} Query SeLinux Status Success. Status: {selinux_status}")
            return selinux_status == "Enforcing"
        except Exception as err:
            logger.exception(f"Device: {device_serial} Query SeLinux Status Fail! ADB Cmd Fail!")
            return None

    def query_android_security_patch_status(self, device_serial):
        """
        Get Android security patch level
        
        Args:
            device_serial: Device serial ID or placeholder
            
        Returns:
            Security patch date as string, or None on error
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")    

        try:
            security_patch = adb.process(['getprop', 'ro.build.version.security_patch']).recvall().decode('utf-8').strip()
            logger.info(f"Device: {device_serial} Query Security Patch Status Success. Status: {security_patch}")
            return security_patch
        except Exception as err:
            logger.exception(f"Device: {device_serial} Query Security Patch Status Fail!")
            return None

    def query_android_webview_version(self, device_serial):
        """
        Get WebView version on the device
        
        Args:
            device_serial: Device serial ID or placeholder
            
        Returns:
            WebView version as string, or None on error
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")    
            
        try:
            # Try Android WebView
            result1 = self.shell_cmd(device_serial, "dumpsys package com.android.webview | grep versionName", False)
            logger.info(f"Device: {device_serial} Query Package com.android.webview Finish. Result: {result1}")

            # Try Google WebView
            result2 = self.shell_cmd(device_serial, "dumpsys package com.google.android.webview | grep versionName", False)
            logger.info(f"Device: {device_serial} Query Package com.google.android.webview Finish. Result: {result2}")

            # Return the first valid result
            version = result1 if result1 else result2
            
            if not version:
                raise_err("未找到webview")
                
            return version
        
        except Exception as err:
            logger.exception(f"Device: {device_serial} Dumpsys Packages Fail!")
            return None

    def list_debug_apps(self, device_serial, keylist):
        """
        Find apps matching debug/test keywords
        
        Args:
            device_serial: Device serial ID or placeholder
            keylist: List of keywords to search for in package names
            
        Returns:
            List of matching package names, or None on error
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev is None:
            raise_err(f"Device {device_serial} Connect Fail!")    
        
        try:
            app_list = []
            for key in keylist:
                packages = self.shell_cmd(device_serial, f"pm list packages | grep -i {key}", False)
                for package_line in packages.splitlines():
                    package_item = package_line.replace("package:", "")
                    if package_item and package_item not in app_list:
                        app_list.append(package_item)
            
            logger.info(f"Device: {device_serial} List Installed Test APPs Success. APPs: {app_list}")
            return app_list
        except Exception as err:
            logger.exception(f"Device: {device_serial} List Installed Test APPs Fail!")
            return None
