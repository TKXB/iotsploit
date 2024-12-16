#!/usr/bin/env python
import os
import logging
import subprocess
from pathlib import Path
import shutil
from typing import Optional, List, Dict
import json

logger = logging.getLogger(__name__)

class FirmwareManager:
    _instance = None
    
    def __init__(self):
        self.esptool_path = shutil.which('esptool.py')
        if not self.esptool_path:
            logger.warning("esptool.py not found in PATH. Please install it using: pip install esptool")
        self.firmware_dir = Path('firmware')
        self.firmware_dir.mkdir(exist_ok=True)
        self.manifest_file = self.firmware_dir / 'firmware_manifest.json'
        self.manifests = self._load_manifests()

    @classmethod
    def Instance(cls):
        if cls._instance is None:
            cls._instance = FirmwareManager()
        return cls._instance

    def _load_manifests(self) -> Dict:
        """Load firmware manifests from JSON file"""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error("Error loading firmware manifest file")
                return {}
        return {}

    def _save_manifests(self):
        """Save firmware manifests to JSON file"""
        try:
            with open(self.manifest_file, 'w') as f:
                json.dump(self.manifests, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving firmware manifest: {str(e)}")

    def init_workspace(self, name: str) -> bool:
        """Initialize a new West workspace"""
        try:
            workspace_path = self.firmware_dir / name
            if workspace_path.exists():
                logger.warning(f"Workspace {name} already exists")
                return False

            cmd = [self.west_path, 'init', '-m', str(workspace_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully initialized workspace: {name}")
                return True
            else:
                logger.error(f"Failed to initialize workspace: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing workspace: {str(e)}")
            return False

    def add_firmware(self, name: str, path: str, device_type: str, version: str) -> bool:
        """Add firmware to manifest"""
        try:
            firmware_path = Path(path)
            if not firmware_path.exists():
                logger.error(f"Firmware file not found: {path}")
                return False

            firmware_info = {
                "path": str(firmware_path),
                "device_type": device_type,
                "version": version
            }

            self.manifests[name] = firmware_info
            self._save_manifests()
            logger.info(f"Successfully added firmware: {name}")
            return True

        except Exception as e:
            logger.error(f"Error adding firmware: {str(e)}")
            return False

    def list_firmware(self) -> List[Dict]:
        """List all available firmware"""
        return [{"name": name, **info} for name, info in self.manifests.items()]

    def flash_firmware(self, name: str, port: Optional[str] = None) -> bool:
        """Flash firmware using esptool"""
        try:
            if not self.esptool_path:
                logger.error("esptool.py not found. Please install it using: pip install esptool")
                return False

            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            firmware_info = self.manifests[name]
            device_type = firmware_info.get('device_type', '').lower()
            firmware_path = firmware_info['path']

            if 'esp32' in device_type:
                cmd = [
                    self.esptool_path,
                    '--chip', 'esp32',
                    '--port', port or '/dev/ttyUSB0',
                    '--baud', '921600',
                    'write_flash',
                    '--flash_mode', 'dio',
                    '--flash_freq', '40m',
                    '--flash_size', 'detect',
                    '0x0', firmware_path
                ]
            else:
                logger.error(f"Unsupported device type: {device_type}. Only ESP32 devices are supported.")
                return False

            logger.info(f"Flashing firmware: {name}")
            logger.info(f"Command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully flashed firmware: {name}")
                return True
            else:
                logger.error(f"Failed to flash firmware: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error flashing firmware: {str(e)}")
            return False

    def remove_firmware(self, name: str) -> bool:
        """Remove firmware from manifest"""
        try:
            if name not in self.manifests:
                logger.error(f"Firmware not found: {name}")
                return False

            del self.manifests[name]
            self._save_manifests()
            logger.info(f"Successfully removed firmware: {name}")
            return True

        except Exception as e:
            logger.error(f"Error removing firmware: {str(e)}")
            return False

    def get_firmware_info(self, name: str) -> Optional[Dict]:
        """Get information about specific firmware"""
        return self.manifests.get(name) 