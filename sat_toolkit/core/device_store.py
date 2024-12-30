from typing import Dict, Optional
import logging
from sat_toolkit.models.Device_Model import Device, DeviceType, SerialDevice, USBDevice, SocketCANDevice
from sat_toolkit.core.device_config import DeviceConfigManager

logger = logging.getLogger(__name__)

class DeviceStore:
    def __init__(self):
        self.devices = {}
        self.device_sources = {}  # tracks if device is static or dynamic
        self.config_manager = DeviceConfigManager()
        
    def register_device(self, device: Device, source: str = "dynamic"):
        """注册设备并保存其配置"""
        self.devices[device.device_id] = device
        self.device_sources[device.device_id] = source
        
    def get_device(self, device_id: str) -> Optional[Device]:
        device = self.devices.get(device_id)
        if not device:
            config = self.config_manager.get_device_config(device_id)
            if config:
                return self._dict_to_device(config)
        return device
        
    def _device_to_dict(self, device: Device) -> Dict:
        """将设备对象转换为字典"""
        base_dict = {
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type.value,
            "attributes": device.attributes
        }
        
        # 根据设备类型添加特定属性
        if isinstance(device, SerialDevice):
            base_dict.update({
                "port": device.port,
                "baud_rate": device.baud_rate
            })
        elif isinstance(device, USBDevice):
            base_dict.update({
                "vendor_id": device.vendor_id,
                "product_id": device.product_id
            })
        elif isinstance(device, SocketCANDevice):
            base_dict.update({
                "interface": device.interface
            })
            
        return base_dict
        
    def _dict_to_device(self, data: Dict) -> Device:
        """从字典创建设备对象"""
        device_type = DeviceType(data["device_type"])
        
        if device_type == DeviceType.Serial:
            return SerialDevice(
                device_id=data["device_id"],
                name=data["name"],
                port=data.get("port", ""),
                baud_rate=data.get("baud_rate", 115200),
                attributes=data.get("attributes", {})
            )
        elif device_type == DeviceType.USB:
            return USBDevice(
                device_id=data["device_id"],
                name=data["name"],
                vendor_id=data.get("vendor_id", ""),
                product_id=data.get("product_id", ""),
                attributes=data.get("attributes", {})
            )
        elif device_type == DeviceType.CAN:
            return SocketCANDevice(
                device_id=data["device_id"],
                name=data["name"],
                interface=data.get("interface", "can0"),
                attributes=data.get("attributes", {})
            )
        else:
            return Device(
                device_id=data["device_id"],
                name=data["name"],
                device_type=device_type,
                attributes=data.get("attributes", {})
            ) 