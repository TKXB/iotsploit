"""WiFi adapter for operating systems without an IoTSploit backend."""

from iotsploit_core.ports.wifi_backend import WifiBackend
from iotsploit_core.utils.exceptions import NotSupportedError


class NullWifiBackend(WifiBackend):
    """Expose the WiFi contract while reporting every operation unsupported."""

    def __init__(self, wifi_iface_name=None):
        self.wifi_iface_name = wifi_iface_name

    @staticmethod
    def _unsupported():
        raise NotSupportedError("WiFi is not supported on this platform")

    def scan(self):
        return self._unsupported()

    def sta_connect(self, ssid, passwd):
        return self._unsupported()

    def sta_disconnect(self):
        return self._unsupported()

    def ap_start(self, ssid=None, passwd=None, wpa_mode=2):
        return self._unsupported()

    def ap_stop(self):
        return self._unsupported()


wifi_backend = NullWifiBackend
