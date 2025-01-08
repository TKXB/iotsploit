from django.apps import AppConfig
from django.core.signals import request_finished
from django.db.models.signals import pre_migrate
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from sat_toolkit.tools.xlogger import xlog as logger


class SatToolkitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sat_toolkit'
    
    # 添加类变量来存储设备管理器和已连接设备的引用
    device_manager = None
    connected_devices = {}

    def ready(self):
        """
        在Django应用程序准备就绪时执行设备初始化
        注意: 在开发环境中,这个方法可能会被调用两次(因为自动重载)
        """
        # 避免在自动重载时重复初始化
        import sys
        if 'runserver' not in sys.argv or '--noreload' in sys.argv:
            self._initialize_devices()
            self._register_shutdown_handlers()

    def _register_shutdown_handlers(self):
        """注册关闭处理程序"""
        import atexit
        
        # 注册系统退出时的清理函数
        atexit.register(self._cleanup_devices)
        
        # 注册Django信号处理
        request_finished.connect(self._cleanup_on_shutdown)
        pre_migrate.connect(self._cleanup_on_shutdown)
        user_logged_out.connect(self._cleanup_on_shutdown)

    def _cleanup_on_shutdown(self, sender, **kwargs):
        """在Django关闭时清理设备"""
        self._cleanup_devices()

    def _cleanup_devices(self):
        """清理所有设备连接"""
        if not self.connected_devices:
            return

        logger.info("Django application: Cleaning up device connections...")
        for driver_name, device in list(self.connected_devices.items()):
            try:
                if self.device_manager:
                    result = self.device_manager.close_device(driver_name, device)
                    if result['status'] == 'success':
                        logger.info(f"Successfully closed {device.name}")
                        del self.connected_devices[driver_name]
                    else:
                        logger.error(f"Failed to close {device.name}: {result['message']}")
            except Exception as e:
                logger.error(f"Error closing {device.name}: {str(e)}")

    def _initialize_devices(self):
        """初始化所有可用设备"""
        try:
            from sat_toolkit.core.device_manager import DeviceDriverManager
            
            logger.info("Django application: Starting automatic device initialization...")
            
            # 初始化设备驱动管理器并存储引用
            self.device_manager = DeviceDriverManager()
            self.connected_devices.clear()
            
            # 获取所有可用驱动
            available_drivers = list(self.device_manager.drivers.keys())
            if not available_drivers:
                logger.warning("No device drivers available!")
                return

            logger.info(f"Found {len(available_drivers)} drivers: {', '.join(available_drivers)}")

            # 遍历每个驱动进行初始化
            for driver_name in available_drivers:
                try:
                    logger.info(f"Initializing {driver_name}...")
                    
                    # 扫描设备
                    scan_result = self.device_manager.scan_devices(driver_name)
                    if scan_result['status'] != 'success':
                        logger.error(f"Failed to scan {driver_name}: {scan_result.get('message', 'Unknown error')}")
                        continue
                    
                    devices = scan_result.get('devices', [])
                    if not devices:
                        logger.warning(f"No devices found for {driver_name}")
                        continue

                    logger.info(f"Found {len(devices)} device(s) for {driver_name}")

                    # 处理每个设备
                    for device in devices:
                        try:
                            logger.info(f"Processing device: {device.name} (ID: {device.device_id})")

                            # 初始化设备
                            init_result = self.device_manager.initialize_device(driver_name, device)
                            if init_result['status'] != 'success':
                                logger.error(f"Failed to initialize {device.name}: {init_result['message']}")
                                continue

                            # 连接设备
                            connect_result = self.device_manager.connect_device(driver_name, device)
                            if connect_result['status'] != 'success':
                                logger.error(f"Failed to connect {device.name}: {connect_result['message']}")
                                continue

                            self.connected_devices[driver_name] = device
                            logger.info(f"Successfully connected {device.name} using {driver_name}")

                        except Exception as e:
                            logger.error(f"Error processing device: {str(e)}")

                except Exception as e:
                    logger.error(f"Error initializing {driver_name}: {str(e)}")
            
            # 显示初始化摘要
            self._show_initialization_summary()

        except Exception as e:
            logger.error(f"Error in device initialization: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)

    def _show_initialization_summary(self):
        """显示设备初始化摘要"""
        logger.info("Device Initialization Summary:")
        
        for driver_name, driver in self.device_manager.drivers.items():
            logger.info("")
            logger.info(f"{driver_name}:")
            
            current_device = self.connected_devices.get(driver_name)
            
            if current_device:
                state = self.device_manager.get_device_state(
                    driver_name, 
                    device_id=current_device.device_id
                )
                logger.info(f"  Device: {current_device.name}")
                logger.info(f"  State: {state.value}")
            else:
                logger.info(f"  Device: No device connected")
                logger.info(f"  State: unknown")
                
            commands = self.device_manager.get_supported_commands(driver_name)
            if commands:
                logger.info(f"  Commands: {', '.join(commands.keys())}")
