# your_app/device_manager.py

import pluggy
import os
import importlib.util
import logging
import threading
from typing import Dict, List, Optional, Any
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.core.device_spec import DeviceState
from sat_toolkit.config import DEVICE_PLUGINS_DIR

logger = logging.getLogger(__name__)

class DeviceDriverManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DeviceDriverManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info("Initializing DeviceDriverManager")
            self.pm = pluggy.PluginManager("device_mgr")
            self.pm.add_hookspecs(DevicePluginSpec)
            self.plugins = {}
            self.drivers = {}  # 存储驱动实例
            self.device_states = {}  # 存储设备状态
            self._connection_locks = {}  # 设备操作锁
            
            # 定义合法的状态转换
            self._state_transitions = {
                DeviceState.UNKNOWN: [DeviceState.DISCOVERED],
                DeviceState.DISCOVERED: [DeviceState.INITIALIZED],
                DeviceState.INITIALIZED: [DeviceState.CONNECTED, DeviceState.DISCONNECTED],
                DeviceState.CONNECTED: [DeviceState.ACTIVE, DeviceState.DISCONNECTED],
                DeviceState.ACTIVE: [DeviceState.CONNECTED, DeviceState.ERROR],
                DeviceState.ERROR: [DeviceState.DISCONNECTED],
                DeviceState.DISCONNECTED: [DeviceState.INITIALIZED]
            }
            
            self.load_plugins()
            self._initialized = True
            logger.info("DeviceDriverManager initialized")

    def load_plugins(self):
        """加载所有设备驱动插件"""
        plugin_dir = os.path.join(os.path.dirname(__file__), DEVICE_PLUGINS_DIR)
        logger.info(f"Loading device plugins from {plugin_dir}")
        for root, _, files in os.walk(plugin_dir):
            for filename in files:
                if filename.startswith("drv_") and filename.endswith(".py"):
                    self.load_plugin(os.path.join(root, filename))

    def load_plugin(self, filepath: str):
        """加载单个插件"""
        try:
            module_name = os.path.splitext(os.path.basename(filepath))[0]
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 自动注册继承自 BaseDeviceDriver 的类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseDeviceDriver) and 
                    attr != BaseDeviceDriver):
                    driver_instance = attr()
                    self.pm.register(driver_instance)
                    self.plugins[module_name] = module
                    self.drivers[module_name] = driver_instance
                    logger.info(f"Loaded device plugin: {module_name} ({attr_name})")
                    break
        except Exception as e:
            logger.error(f"Failed to load plugin {filepath}: {str(e)}")

    def execute_command(self, driver_name: str, command: str, device_id: str = "", **kwargs) -> Dict:
        """执行设备命令
        
        Args:
            driver_name: 驱动名称 (e.g., 'drv_socketcan')
            command: 要执行的命令
            device_id: 可选的设备ID，用于多设备场景
            **kwargs: 命令参数
        
        Returns:
            Dict: 包含操作结果的字典
        """
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='command',
            device_id=device_id,
            command=command,
            args=kwargs
        )

    def scan_devices(self, driver_name: str) -> Dict:
        """扫描设备"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='scan'
        )

    def initialize_device(self, driver_name: str, device: Device) -> Dict:
        """初始化设备"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='initialize',
            device=device
        )

    def connect_device(self, driver_name: str, device: Device) -> Dict:
        """连接设备"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='connect',
            device=device
        )

    def reset_device(self, driver_name: str, device: Device) -> Dict:
        """重置设备"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='reset',
            device=device
        )

    def close_device(self, driver_name: str, device: Device) -> Dict:
        """关闭设备"""
        return self._manage_device_lifecycle(
            driver_name=driver_name,
            action='close',
            device=device
        )

    def get_device_state(self, driver_name: str, device_id: str = "") -> DeviceState:
        """获取设备当前状态"""
        device_key = self._get_device_key(driver_name, device_id=device_id)
        return self._get_device_state(device_key)

    def get_supported_commands(self, driver_name: str) -> Dict[str, str]:
        """获取设备支持的命令"""
        driver = self.get_driver_instance(driver_name)
        if driver:
            return driver.get_supported_commands()
        return {}

    def get_plugin_commands(self, plugin_name: str) -> Dict[str, str]:
        """获取插件支持的命令列表
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Dict[str, str]: 命令名称和描述的字典
        """
        driver = self.get_driver_instance(plugin_name)
        if driver:
            return driver.get_supported_commands()
        return {}

    def _manage_device_lifecycle(self, driver_name: str, action: str, **kwargs) -> Dict:
        """内部使用的设备生命周期管理方法"""
        try:
            driver = self.get_driver_instance(driver_name)
            if not driver:
                return {
                    "status": "error",
                    "message": f"Driver {driver_name} not found"
                }

            device = kwargs.get('device')
            device_id = kwargs.get('device_id', '')
            if device and hasattr(device, 'device_id'):
                device_id = device.device_id

            device_key = f"{driver_name}_{device_id}"

            with self._get_device_lock(device_key):
                current_state = self._get_device_state(device_key)
                
                # 修改状态转换逻辑
                if action != 'scan':
                    if action == 'initialize':
                        # 对于初始化操作，只在未初始化状态下执行
                        if current_state not in [DeviceState.UNKNOWN, DeviceState.DISCOVERED]:
                            return {
                                "status": "error",
                                "message": f"Cannot perform initialize in current state {current_state}. Expected states: [unknown, discovered]"
                            }
                    elif action == 'connect':
                        # 对于连接操作，确保设备已初始化
                        if current_state == DeviceState.UNKNOWN:
                            # 自动扫描
                            scan_result = self._handle_scan(driver, driver_name, **kwargs)
                            if scan_result["status"] != "success":
                                return scan_result
                            current_state = self._get_device_state(device_key)
                        
                        if current_state == DeviceState.DISCOVERED:
                            # 只在发现状态时执行初始化
                            init_result = self._handle_initialize(driver, driver_name, **kwargs)
                            if init_result["status"] != "success":
                                return init_result
                            current_state = self._get_device_state(device_key)
                        
                        if current_state != DeviceState.INITIALIZED:
                            return {
                                "status": "error",
                                "message": f"Cannot connect device in state {current_state}. Expected state: initialized"
                            }

                return self._execute_action(driver, action, current_state, device_key, driver_name, **kwargs)

        except Exception as e:
            logger.error(f"Lifecycle management failed: {str(e)}", exc_info=True)
            self._update_device_state(device_key, DeviceState.ERROR)
            return {
                "status": "error",
                "message": str(e)
            }

    def _get_device_lock(self, device_key: str) -> threading.Lock:
        """获取设备操作锁"""
        if device_key not in self._connection_locks:
            self._connection_locks[device_key] = threading.Lock()
        return self._connection_locks[device_key]

    def _get_device_state(self, device_key: str) -> DeviceState:
        """获取设备当前状态"""
        return self.device_states.get(device_key, DeviceState.UNKNOWN)

    def _update_device_state(self, device_key: str, new_state: DeviceState):
        """更新设备状态"""
        current_state = self._get_device_state(device_key)
        
        if current_state == new_state:
            return
        
        if new_state in self._state_transitions.get(current_state, []):
            self.device_states[device_key] = new_state
            logger.info(f"Device {device_key} state changed: {current_state} -> {new_state}")
        else:
            # 特殊处理：如果设备已经处于更高级的状态，不要降级
            state_hierarchy = {
                DeviceState.UNKNOWN: 0,
                DeviceState.DISCOVERED: 1,
                DeviceState.INITIALIZED: 2,
                DeviceState.CONNECTED: 3,
                DeviceState.ACTIVE: 4,
            }
            
            # 只有当新状态的等级高于当前状态时才更新
            if state_hierarchy.get(new_state, 0) > state_hierarchy.get(current_state, 0):
                self.device_states[device_key] = new_state
                logger.info(f"Device {device_key} state upgraded: {current_state} -> {new_state}")
            else:
                logger.info(f"Ignoring state transition: {current_state} -> {new_state}")

    def _execute_action(self, 
                        driver: BaseDeviceDriver, 
                        action: str, 
                        current_state: DeviceState, 
                        device_key: str, 
                        driver_name: str,
                        **kwargs) -> Dict:
        """执行具体的动作"""
        try:
            if action == 'scan':
                return self._handle_scan(driver, driver_name, **kwargs)
            elif action == 'initialize':
                return self._handle_initialize(driver, driver_name, **kwargs)
            elif action == 'connect':
                return self._handle_connect(driver, driver_name, **kwargs)
            elif action == 'command':
                return self._handle_command(driver, driver_name, device_key, **kwargs)
            elif action == 'reset':
                return self._handle_reset(driver, driver_name, **kwargs)
            elif action == 'close':
                return self._handle_close(driver, driver_name, **kwargs)
            else:
                return {"status": "error", "message": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            self._update_device_state(device_key, DeviceState.ERROR)
            return {"status": "error", "message": str(e)}

    def _get_device_key(self, driver_name: str, device: Device = None, device_id: str = "") -> str:
        """统一生成设备键值的方法"""
        if device:
            key = f"{driver_name}_{device.device_id}"
        else:
            key = f"{driver_name}_{device_id}"
        return key

    def _handle_scan(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """处理扫描操作"""
        try:
            devices = driver.scan()
            for device in devices:
                device_key = f"{driver_name}_{device.device_id}"
                self._update_device_state(device_key, DeviceState.DISCOVERED)
            return {
                "status": "success",
                "devices": devices
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_initialize(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """处理初始化操作"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}

            success = driver.initialize(device)
            device_key = f"{driver_name}_{device.device_id}"
            if success:
                self._update_device_state(device_key, DeviceState.INITIALIZED)
                return {
                    "status": "success",
                    "message": "Device initialized"
                }
            return {
                "status": "error",
                "message": "Initialization failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_connect(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """处理连接操作"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}

            success = driver.connect(device)
            device_key = f"{driver_name}_{device.device_id}"
            if success:
                self._update_device_state(device_key, DeviceState.CONNECTED)
                return {
                    "status": "success",
                    "message": "Device connected"
                }
            return {
                "status": "error",
                "message": "Connection failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_command(self, driver: BaseDeviceDriver, driver_name: str, device_key: str, **kwargs) -> Dict:
        """处理命令执行"""
        try:
            command = kwargs.get('command')
            args = kwargs.get('args')
            if not command:
                return {"status": "error", "message": "Command not specified"}

            # Move to ACTIVE
            self._update_device_state(device_key, DeviceState.ACTIVE)

            # Execute the actual command
            result = driver.command(driver.device, command, args)

            # Transition back to CONNECTED
            self._update_device_state(device_key, DeviceState.CONNECTED)

            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            self._update_device_state(device_key, DeviceState.ERROR)
            return {"status": "error", "message": str(e)}

    def _handle_reset(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """处理重置操作"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}
            
            success = driver.reset(device)
            return {
                "status": "success" if success else "error",
                "message": "Device reset" if success else "Reset failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _handle_close(self, driver: BaseDeviceDriver, driver_name: str, **kwargs) -> Dict:
        """处理关闭操作"""
        try:
            device = kwargs.get('device')
            if not device:
                return {"status": "error", "message": "Device not specified"}
            
            success = driver.close(device)
            return {
                "status": "success" if success else "error",
                "message": "Device closed" if success else "Close failed"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_driver_instance(self, plugin_name: str) -> Optional[BaseDeviceDriver]:
        """获取驱动实例"""
        return self.drivers.get(plugin_name)

    def list_drivers(self) -> List[str]:
        """获取所有已加载的驱动列表
        
        Returns:
            List[str]: 驱动名称列表
        """
        return list(self.drivers.keys())

