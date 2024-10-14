import logging
import platform
import socket
import psutil
import netifaces
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class DeviceMonitor(ABC):
    @abstractmethod
    def get_system_info(self):
        pass

    @abstractmethod
    def get_cpu_temperature(self):
        pass

    @abstractmethod
    def get_battery_status(self):
        pass

class LinuxMonitor(DeviceMonitor):
    def get_system_info(self):
        return {
            "uname": platform.uname(),
            "hostname": socket.gethostname(),
            "ip_addresses": self._get_ip_addresses(),
        }

    def get_cpu_temperature(self):
        try:
            temp = psutil.sensors_temperatures()['coretemp'][0].current
            return f"{temp:.1f}°C"
        except:
            return "N/A"

    def get_battery_status(self):
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": f"{battery.percent:.1f}%",
                "power_plugged": battery.power_plugged,
                "time_left": self._format_battery_time(battery.secsleft)
            }
        return {"status": "No battery detected"}

    def _get_ip_addresses(self):
        ip_addresses = {}
        for interface in netifaces.interfaces():
            try:
                ip = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr']
                ip_addresses[interface] = ip
            except:
                pass
        return ip_addresses

    def _format_battery_time(self, seconds):
        if seconds == psutil.POWER_TIME_UNLIMITED:
            return "Unlimited"
        if seconds == psutil.POWER_TIME_UNKNOWN:
            return "Unknown"
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

class Pi_Mgr(LinuxMonitor):
    def get_cpu_temperature(self):
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as temp_file:
                temp = float(temp_file.read().strip()) / 1000
                return f"{temp:.1f}°C"
        except:
            return super().get_cpu_temperature()

    def get_battery_status(self):
        # Implement Raspberry Pi specific battery monitoring if available
        # For now, we'll use the Linux implementation
        return super().get_battery_status()

class MCUMonitor(DeviceMonitor):
    def __init__(self, connection):
        self.connection = connection  # This could be a serial connection or other interface to the MCU

    def get_system_info(self):
        # Implement MCU-specific system info retrieval
        # This is just a placeholder and should be implemented based on your MCU's capabilities
        return {
            "device_type": "MCU",
            "firmware_version": self._get_firmware_version(),
        }

    def get_cpu_temperature(self):
        # Implement MCU-specific temperature reading
        # This is just a placeholder
        return self._send_command("GET_TEMP")

    def get_battery_status(self):
        # Implement MCU-specific battery status reading
        # This is just a placeholder
        return self._send_command("GET_BATTERY")

    def _get_firmware_version(self):
        # Implement firmware version retrieval
        return self._send_command("GET_VERSION")

    def _send_command(self, command):
        # Implement the logic to send a command to the MCU and receive the response
        # This is just a placeholder
        self.connection.write(command.encode())
        return self.connection.readline().decode().strip()

class SystemMonitor:
    @staticmethod
    def create_monitor(device_type, **kwargs):
        if device_type == "linux":
            return LinuxMonitor()
        elif device_type == "raspberry_pi":
            return Pi_Mgr()
        elif device_type == "mcu":
            if 'connection' not in kwargs:
                raise ValueError("MCU monitor requires a connection object")
            return MCUMonitor(kwargs['connection'])
        else:
            raise ValueError(f"Unsupported device type: {device_type}")

    @staticmethod
    def monitor_device(device_monitor):
        info = device_monitor.get_system_info()
        info['cpu_temperature'] = device_monitor.get_cpu_temperature()
        info['battery_status'] = device_monitor.get_battery_status()
        return info

# Usage example
if __name__ == "__main__":
    # Monitor a Linux PC
    linux_monitor = SystemMonitor.create_monitor("linux")
    linux_info = SystemMonitor.monitor_device(linux_monitor)
    print(f"Linux System Info: {linux_info}")

    # Monitor a Raspberry Pi
    pi_monitor = SystemMonitor.create_monitor("raspberry_pi")
    pi_info = SystemMonitor.monitor_device(pi_monitor)
    print(f"Raspberry Pi Info: {pi_info}")

    # Monitor an MCU (assuming you have a connection object)
    # mcu_connection = create_mcu_connection()  # You'd need to implement this
    # mcu_monitor = SystemMonitor.create_monitor("mcu", connection=mcu_connection)
    # mcu_info = SystemMonitor.monitor_device(mcu_monitor)
    # print(f"MCU Info: {mcu_info}")
