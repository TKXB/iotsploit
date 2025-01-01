from typing import Dict, Optional, List
import logging
from sat_toolkit.models.Device_Model import Device, DeviceType
from sat_toolkit.core.device_config import DeviceConfigManager
from sat_toolkit.core.device_manager import DeviceDriverManager
from sat_toolkit.core.device_scanner import CompositeDeviceScanner, PluginDeviceScanner
from sat_toolkit.core.device_store import DeviceStore

logger = logging.getLogger(__name__)

class DeviceRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.device_store = DeviceStore()
            self.config_manager = DeviceConfigManager()
            self.driver_manager = DeviceDriverManager()
            self.scanner = CompositeDeviceScanner(self.device_store)
            self._initialized = True
            
    def initialize(self):
        """初始化设备注册表"""
        logger.debug("Initializing device registry...")
        
        # 清理现有的扫描器
        self.scanner.clear_scanners()
        
        # 为每个驱动创建扫描器
        for driver_name, driver in self.driver_manager.drivers.items():
            scanner = PluginDeviceScanner(self.device_store, driver)
            self.scanner.add_scanner(scanner)
            logger.debug(f"Added scanner for driver: {driver_name}")
            
        # 加载配置的设备
        try:
            stored_configs = self.config_manager.load_configs()
            if stored_configs.get('devices'):
                for device_config in stored_configs['devices']:
                    try:
                        device = self.device_store._dict_to_device(device_config)
                        self.device_store.register_device(device, source="static")
                        logger.debug(f"Loaded static device: {device.device_id}")
                    except Exception as e:
                        logger.error(f"Error loading device from config: {e}")
        except Exception as e:
            logger.error(f"Error loading stored configurations: {e}")
            
    def scan_devices(self) -> List[Device]:
        """扫描所有可用设备"""
        try:
            discovered_devices = self.scanner.scan()
            # 注册发现的设备
            for device in discovered_devices:
                try:
                    self.device_store.register_device(device, source="dynamic")
                except Exception as e:
                    logger.error(f"Error registering discovered device: {e}")
            return discovered_devices
        except Exception as e:
            logger.error(f"Error during device scan: {e}")
            return []
        
    def merge_devices(self, stored_configs: Dict, discovered_devices: List[Device]):
        """合并存储的配置和发现的设备"""
        # 处理发现的设备
        for device in discovered_devices:
            try:
                self.device_store.register_device(device, source="dynamic")
            except Exception as e:
                logger.error(f"Error registering dynamic device: {e}")
            
        # 处理存储的配置
        if stored_configs.get('devices'):
            for device_config in stored_configs['devices']:
                try:
                    device_id = device_config.get('device_id')
                    if device_id and device_id not in self.device_store.devices:
                        device = self.device_store._dict_to_device(device_config)
                        self.device_store.register_device(device, source="static")
                except Exception as e:
                    logger.error(f"Error registering static device: {e}") 