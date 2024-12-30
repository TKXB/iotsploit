import os
import json
from typing import Dict, Optional
import logging
from sat_toolkit.models.Device_Model import Device, DeviceType
from json import JSONEncoder

logger = logging.getLogger(__name__)

class DeviceJSONEncoder(JSONEncoder):
    """自定义JSON编码器，处理特殊类型的序列化"""
    def default(self, obj):
        if isinstance(obj, DeviceType):
            return obj.value
        if isinstance(obj, Device):
            # 使用 DeviceStore 中的序列化方法
            from sat_toolkit.core.device_store import DeviceStore
            return DeviceStore()._device_to_dict(obj)
        return super().default(obj)

class DeviceConfigManager:
    """设备配置管理器"""
    
    def __init__(self):
        self.config_file = "conf/devices.json"
        
    def load_configs(self) -> Dict[str, Dict]:
        """加载设备配置"""
        if not os.path.exists(self.config_file):
            return {"devices": []}
            
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {self.config_file}: {e}")
            return {"devices": []}
        except Exception as e:
            logger.error(f"Error loading config file {self.config_file}: {e}")
            return {"devices": []}
            
    def save_device_config(self, device_dict: Dict):
        """保存设备配置到持久化存储"""
        try:
            configs = self.load_configs()
            # 确保configs中有devices键
            if 'devices' not in configs:
                configs['devices'] = []
            
            # 更新或添加设备配置
            device_id = device_dict['device_id']
            device_updated = False
            for i, device in enumerate(configs['devices']):
                if device.get('device_id') == device_id:
                    configs['devices'][i] = device_dict
                    device_updated = True
                    break
                
            if not device_updated:
                configs['devices'].append(device_dict)
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(configs, f, indent=2, cls=DeviceJSONEncoder)
                
        except Exception as e:
            logger.error(f"Error saving device configuration: {e}")
            
    def get_device_config(self, device_id: str) -> Optional[Dict]:
        """获取特定设备的配置"""
        configs = self.load_configs()
        for device in configs.get('devices', []):
            if device.get('device_id') == device_id:
                return device
        return None 