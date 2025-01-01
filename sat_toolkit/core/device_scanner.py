from typing import List, Dict, Type
import logging
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.device_store import DeviceStore
from sat_toolkit.core.base_plugin import BaseDeviceDriver

logger = logging.getLogger(__name__)

class DeviceScanner:
    """设备扫描器基类"""
    def __init__(self, device_store: DeviceStore):
        self.device_store = device_store
        
    def scan(self) -> List[Device]:
        """执行设备扫描"""
        return self._perform_scan()
        
    def _perform_scan(self) -> List[Device]:
        """实际的扫描实现"""
        raise NotImplementedError("Subclasses must implement _perform_scan()")

class PluginDeviceScanner(DeviceScanner):
    """使用插件系统的设备扫描器"""
    def __init__(self, device_store: DeviceStore, driver: BaseDeviceDriver):
        super().__init__(device_store)
        self.driver = driver
        
    def _perform_scan(self) -> List[Device]:
        """使用驱动执行扫描"""
        try:
            logger.info(f"Scanning devices using driver: {self.driver.__class__.__name__}")
            result = self.driver.scan()
            
            if not result:
                logger.info("No devices found")
                return []
                
            # 确保返回列表
            devices = result if isinstance(result, list) else [result]
            
            # 注册发现的设备
            for device in devices:
                self.device_store.register_device(device, source="dynamic")
                
            return devices
                
        except Exception as e:
            logger.error(f"Error scanning devices: {str(e)}")
            return []

class CompositeDeviceScanner(DeviceScanner):
    """组合多个扫描器的复合扫描器"""
    def __init__(self, device_store: DeviceStore):
        super().__init__(device_store)
        self.scanners: List[DeviceScanner] = []
        
    def clear_scanners(self):
        """清理所有已注册的扫描器"""
        self.scanners = []
        
    def add_scanner(self, scanner: DeviceScanner):
        """添加一个扫描器"""
        self.scanners.append(scanner)
        
    def _perform_scan(self) -> List[Device]:
        """执行所有注册的扫描器"""
        all_devices = []
        for scanner in self.scanners:
            try:
                # 直接调用 _perform_scan 避免重复注册
                devices = scanner._perform_scan()
                all_devices.extend(devices)
            except Exception as e:
                logger.error(f"Error in scanner {scanner.__class__.__name__}: {str(e)}")
                continue
                
        return all_devices 