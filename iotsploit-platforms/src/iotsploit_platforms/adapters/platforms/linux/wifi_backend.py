"""
Linux WiFi Backend Implementation.

This module provides Linux-specific WiFi backend implementation using
NetworkManager's native libnm API via GObject Introspection.
"""

import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

import gi
gi.require_version('NM', '1.0')
from gi.repository import NM, GLib

from iotsploit_core.ports.wifi_backend import WifiBackend
from iotsploit_core.utils.exceptions import NotSupportedError

logger = logging.getLogger(__name__)

# NetworkManager DBus constants (from NM headers / docs)
_NM_ACTIVE_CONNECTION_STATE_ACTIVATED = 2


class LinuxWifiBackend(WifiBackend):
    """
    Linux WiFi backend implementation using NetworkManager.
    
    Uses libnm (NetworkManager's native library) for all WiFi operations.
    Supports station mode, access point mode, and network scanning.
    """
    # Keep consistent with upstream DBus hotspot example
    _HOTSPOT_UUID = "2b0d0f1d-b79d-43af-bde1-71744625642e"

    def __init__(self, wifi_iface_name: str = "wlan0", forward_eth_name: Optional[str] = None):
        """
        Initialize NetworkManager WiFi backend.
        
        Args:
            wifi_iface_name: WiFi interface name (e.g., "wlan0", "wlp0s20f3")
            forward_eth_name: Ethernet interface for forwarding (used for AP mode NAT)
        """
        self.wifi_iface_name = wifi_iface_name
        self.forward_eth_name = forward_eth_name
        
        self._wifi_mode = "IDLE"
        self._sta_conn_wifi_ssid = ""
        self._sta_conn_wifi_passwd = ""
        self._ap_ssid = ""
        self._ap_passwd = ""
        
        # Connection IDs for tracking
        self._active_connection_id: Optional[str] = None
        self._hotspot_connection_id: Optional[str] = None
        # Hotspot connection UUID/path (DBus profile reuse)
        self._hotspot_connection_uuid: Optional[str] = None
        self._hotspot_connection_path: Optional[str] = None
        self._hotspot_active_connection_path: Optional[str] = None
        
        # Initialize NetworkManager client
        self._client: Optional[NM.Client] = None
        self._device: Optional[NM.DeviceWifi] = None
        self._init_client()

    def _init_client(self):
        """Initialize NetworkManager client and find WiFi device."""
        try:
            self._client = NM.Client.new(None)
            self._device = self._find_wifi_device()
            logger.info(f"NetworkManager client initialized for {self.wifi_iface_name}")
        except Exception as e:
            logger.error(f"Failed to initialize NetworkManager client: {e}")
            raise NotSupportedError(f"NetworkManager initialization failed: {e}")

    def _find_wifi_device(self) -> NM.DeviceWifi:
        """Find the WiFi device by interface name."""
        devices = self._client.get_devices()
        for device in devices:
            if device.get_iface() == self.wifi_iface_name:
                if isinstance(device, NM.DeviceWifi):
                    return device
                else:
                    raise NotSupportedError(f"{self.wifi_iface_name} is not a WiFi device")
        
        # List available WiFi devices for debugging
        wifi_devices = [d.get_iface() for d in devices if isinstance(d, NM.DeviceWifi)]
        raise NotSupportedError(
            f"WiFi device {self.wifi_iface_name} not found. "
            f"Available WiFi devices: {wifi_devices}"
        )

    def _get_security_flags_string(self, ap: NM.AccessPoint) -> str:
        """Convert AP security flags to string."""
        wpa_flags = ap.get_wpa_flags()
        rsn_flags = ap.get_rsn_flags()
        
        # Use integer constants instead of enum attributes for compatibility
        # KEY_MGMT_PSK = 0x00000002 (from NetworkManager headers)
        KEY_MGMT_PSK = 0x00000002
        
        if rsn_flags & KEY_MGMT_PSK:
            return "WPA2"
        elif wpa_flags & KEY_MGMT_PSK:
            return "WPA"
        elif ap.get_flags() & 0x0001:  # PRIVACY flag
            return "WEP"
        else:
            return "OPEN"

    def _wait_for_connection(self, timeout: int = 30) -> bool:
        """Wait for connection to be established."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = self._device.get_state()
            if state == NM.DeviceState.ACTIVATED:
                return True
            elif state in (NM.DeviceState.FAILED, NM.DeviceState.DISCONNECTED):
                return False
            time.sleep(0.5)
        return False

    def _find_connection_by_id(self, conn_id: str) -> Optional[NM.RemoteConnection]:
        """Find a connection profile by ID."""
        connections = self._client.get_connections()
        for conn in connections:
            if conn.get_id() == conn_id:
                return conn
        return None

    def _delete_connection_by_id(self, conn_id: str) -> bool:
        """Delete a connection profile by ID."""
        conn = self._find_connection_by_id(conn_id)
        if conn:
            try:
                conn.delete(None)
                logger.info(f"Deleted connection: {conn_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete connection {conn_id}: {e}")
        return False

    def _get_or_make_hotspot_uuid(self) -> str:
        """
        Return a stable UUID for the hotspot profile.

        We intentionally keep the UUID stable across runs so we can reuse the
        same NetworkManager connection profile (per the upstream DBus example).
        """
        # Force using the same UUID as the provided example for consistency.
        self._hotspot_connection_uuid = self._HOTSPOT_UUID
        return self._hotspot_connection_uuid

    def _ensure_hotspot_profile_dbus(
        self,
        ssid: str,
        passwd: str,
        band: str = "bg",
        channel: int = 6,
    ) -> Tuple["dbus.SystemBus", str, str]:
        """
        Ensure a NetworkManager hotspot profile exists (DBus), return (bus, devpath, connection_path).
        """
        try:
            import dbus  # type: ignore
        except Exception as e:  # pragma: no cover
            raise NotSupportedError(f"dbus-python not available: {e}")

        hotspot_uuid = self._get_or_make_hotspot_uuid()

        # Build settings dicts (matches upstream example structure)
        s_con = dbus.Dictionary(
            {
                "type": "802-11-wireless",
                "uuid": hotspot_uuid,
                # Keep a stable, human-readable id in NetworkManager UI
                "id": f"iotsploit-hotspot-{self.wifi_iface_name}",
                "autoconnect": dbus.Boolean(False),
            }
        )

        s_wifi = dbus.Dictionary(
            {
                "ssid": dbus.ByteArray(ssid.encode("utf-8")),
                "mode": "ap",
                "band": band,
                "channel": dbus.UInt32(int(channel)),
            }
        )

        s_ip4 = dbus.Dictionary({"method": "shared"})
        s_ip6 = dbus.Dictionary({"method": "ignore"})

        con: Dict[str, Any] = {
            "connection": s_con,
            "802-11-wireless": s_wifi,
            "ipv4": s_ip4,
            "ipv6": s_ip6,
        }

        # WPA2-PSK (same as example). If passwd empty, we create an open AP.
        if passwd:
            s_wsec = dbus.Dictionary({"key-mgmt": "wpa-psk", "psk": passwd})
            con["802-11-wireless-security"] = s_wsec

        con = dbus.Dictionary(con)

        bus = dbus.SystemBus()

        # Find or create the connection profile under Settings
        settings_proxy = bus.get_object(
            "org.freedesktop.NetworkManager",
            "/org/freedesktop/NetworkManager/Settings",
        )
        settings = dbus.Interface(settings_proxy, "org.freedesktop.NetworkManager.Settings")

        connection_path = None
        for path in settings.ListConnections():
            proxy = bus.get_object("org.freedesktop.NetworkManager", path)
            settings_connection = dbus.Interface(
                proxy,
                "org.freedesktop.NetworkManager.Settings.Connection",
            )
            config = settings_connection.GetSettings()
            if config.get("connection", {}).get("uuid") == hotspot_uuid:
                connection_path = path
                break

        if not connection_path:
            connection_path = settings.AddConnection(con)
            logger.info(f"Created hotspot profile via DBus: uuid={hotspot_uuid} path={connection_path}")
        else:
            logger.info(f"Reusing hotspot profile via DBus: uuid={hotspot_uuid} path={connection_path}")

        # Resolve device path by interface name
        nm_proxy = bus.get_object("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager")
        nm = dbus.Interface(nm_proxy, "org.freedesktop.NetworkManager")
        devpath = nm.GetDeviceByIpIface(self.wifi_iface_name)

        # Cache for stop/status usage
        self._hotspot_connection_path = str(connection_path)

        return bus, str(devpath), str(connection_path)

    def _wait_hotspot_activated_dbus(self, bus: "dbus.SystemBus", acpath: str, timeout: int = 10) -> bool:
        """Wait until the active connection reaches ACTIVATED (DBus)."""
        import dbus  # type: ignore

        proxy = bus.get_object("org.freedesktop.NetworkManager", acpath)
        active_props = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")

        start = time.time()
        while time.time() < start + timeout:
            try:
                state = int(
                    active_props.Get(
                        "org.freedesktop.NetworkManager.Connection.Active",
                        "State",
                    )
                )
            except Exception:
                state = -1
            if state == _NM_ACTIVE_CONNECTION_STATE_ACTIVATED:
                return True
            time.sleep(1)

        return False

    def _get_ap_clients(self) -> List[Dict[str, Any]]:
        """
        Get connected clients from DHCP leases.
        
        NetworkManager uses dnsmasq for DHCP in shared mode.
        This method parses the DHCP lease files to get connected clients.
        """
        client_list = []
        try:
            # NetworkManager stores leases in /var/lib/NetworkManager/dnsmasq-*.leases
            lease_dir = Path("/var/lib/NetworkManager")
            if lease_dir.exists():
                lease_files = list(lease_dir.glob("dnsmasq-*.leases"))
                for lease_file in lease_files:
                    try:
                        with open(lease_file, 'r') as f:
                            for line in f:
                                parts = line.strip().split()
                                if len(parts) >= 4:
                                    client_list.append({
                                        "mac": parts[1],
                                        "ip": parts[2],
                                        "name": parts[3] if len(parts) > 3 else "",
                                    })
                    except Exception as e:
                        logger.warning(f"Failed to read lease file {lease_file}: {e}")
            
            # Fallback: try traditional dnsmasq location
            if not client_list:
                traditional_lease = Path("/var/lib/misc/dnsmasq.leases")
                if traditional_lease.exists():
                    try:
                        with open(traditional_lease, 'r') as f:
                            for line in f:
                                parts = line.strip().split()
                                if len(parts) >= 4:
                                    client_list.append({
                                        "mac": parts[1],
                                        "ip": parts[2],
                                        "name": parts[3] if len(parts) > 3 else "",
                                    })
                    except Exception as e:
                        logger.warning(f"Failed to read traditional lease file: {e}")
        except Exception as e:
            logger.warning(f"Failed to get AP clients from DHCP leases: {e}")
        
        return client_list

    # ==================== Public API ====================

    def scan(self) -> List[Dict[str, Any]]:
        """
        Scan for available WiFi networks.
        
        Returns:
            List of dictionaries containing WiFi network information.
        """
        logger.info("Start WiFi scan via NetworkManager")
        
        # Request a new scan
        try:
            self._device.request_scan(None)
        except Exception as e:
            logger.warning(f"Scan request failed (may already be scanning): {e}")
        
        # Wait for scan to complete
        time.sleep(3)
        
        # Get access points
        access_points = self._device.get_access_points()
        
        result_list = []
        seen_ssids = set()  # Deduplicate by SSID
        
        for ap in access_points:
            ssid_bytes = ap.get_ssid()
            if ssid_bytes is None:
                continue
            
            ssid = ssid_bytes.get_data().decode('utf-8', errors='ignore')
            if not ssid or ssid in seen_ssids:
                continue
            
            seen_ssids.add(ssid)
            
            result_list.append({
                "ssid": ssid,
                "bssid": ap.get_bssid(),
                "signal": ap.get_strength(),
                "security": self._get_security_flags_string(ap),
                "frequency": ap.get_frequency(),
            })
            logger.info(f"Found WiFi: {ssid} ({ap.get_bssid()})")
        
        logger.info(f"Scan complete. Found {len(result_list)} networks.")
        return result_list

    def sta_connect(self, ssid: str, passwd: str) -> None:
        """
        Connect to a WiFi network in station (STA) mode.
        
        Args:
            ssid: Network SSID to connect to
            passwd: Network password (empty string for open networks)
        """
        logger.info(f"Connecting to WiFi: {ssid}")
        
        # Check if already connected to this network
        if (self._wifi_mode == "STA" and 
            self._sta_conn_wifi_ssid == ssid and
            self._sta_conn_wifi_passwd == passwd):
            if self._device.get_state() == NM.DeviceState.ACTIVATED:
                logger.info(f"Already connected to {ssid}, skipping")
                return
        
        # Disconnect any existing connection first
        self.sta_disconnect()
        
        # Store connection info
        self._sta_conn_wifi_ssid = ssid
        self._sta_conn_wifi_passwd = passwd
        
        # Create connection profile
        connection_id = f"iotsploit-{ssid}-{uuid.uuid4().hex[:8]}"
        
        # Build connection settings
        connection = NM.SimpleConnection.new()
        
        # Connection settings
        s_con = NM.SettingConnection.new()
        s_con.set_property(NM.SETTING_CONNECTION_ID, connection_id)
        s_con.set_property(NM.SETTING_CONNECTION_UUID, str(uuid.uuid4()))
        s_con.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
        s_con.set_property(NM.SETTING_CONNECTION_AUTOCONNECT, False)
        connection.add_setting(s_con)
        
        # Wireless settings
        s_wifi = NM.SettingWireless.new()
        s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode('utf-8')))
        s_wifi.set_property(NM.SETTING_WIRELESS_MODE, "infrastructure")
        connection.add_setting(s_wifi)
        
        # Security settings (if password provided)
        if passwd:
            s_wifi_sec = NM.SettingWirelessSecurity.new()
            s_wifi_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk")
            s_wifi_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, passwd)
            connection.add_setting(s_wifi_sec)
        
        # IPv4 settings (auto/DHCP)
        s_ip4 = NM.SettingIP4Config.new()
        s_ip4.set_property(NM.SETTING_IP_CONFIG_METHOD, "auto")
        connection.add_setting(s_ip4)
        
        # IPv6 settings
        s_ip6 = NM.SettingIP6Config.new()
        s_ip6.set_property(NM.SETTING_IP_CONFIG_METHOD, "auto")
        connection.add_setting(s_ip6)
        
        try:
            # Add and activate connection
            self._client.add_and_activate_connection(
                connection,
                self._device,
                None,  # specific_object (AP path, optional)
                None   # cancellable
            )
            
            self._active_connection_id = connection_id
            self._wifi_mode = "STA"
            
            # Wait for connection
            if self._wait_for_connection(timeout=30):
                logger.info(f"Successfully connected to {ssid}")
            else:
                logger.error(f"Connection to {ssid} timed out or failed")
                raise ConnectionError(f"Failed to connect to {ssid}")
                
        except Exception as e:
            logger.error(f"Failed to connect to {ssid}: {e}")
            self._wifi_mode = "IDLE"
            raise ConnectionError(f"Failed to connect to {ssid}: {e}")

    def sta_disconnect(self) -> None:
        """
        Disconnect from the current WiFi network in station mode.
        """
        logger.info("Disconnecting from WiFi")
        
        if self._wifi_mode != "STA":
            logger.info(f"Not in STA mode (current: {self._wifi_mode}), skipping disconnect")
            return
        
        try:
            # Disconnect the device
            self._device.disconnect(None)
            
            # Wait for disconnection
            time.sleep(1)
            
            # Clean up connection profile
            if self._active_connection_id:
                self._delete_connection_by_id(self._active_connection_id)
                self._active_connection_id = None
            
            self._wifi_mode = "IDLE"
            self._sta_conn_wifi_ssid = ""
            self._sta_conn_wifi_passwd = ""
            
            logger.info("Disconnected from WiFi")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            self._wifi_mode = "IDLE"

    def ap_start(self, ssid: Optional[str] = None, passwd: Optional[str] = None, wpa_mode: int = 2) -> Tuple[str, str]:
        """
        Start WiFi access point (AP) mode using NetworkManager hotspot.
        
        Args:
            ssid: AP SSID (if None, a default will be generated)
            passwd: AP password (if None, a default will be used)
            wpa_mode: WPA mode (ignored, NetworkManager uses WPA2 by default)
        
        Returns:
            Tuple of (ssid, passwd) that were actually used
        """
        # First disconnect any existing connection
        self.sta_disconnect()
        self.ap_stop()
        
        # Generate default SSID if not provided
        if ssid is None:
            hw_addr = self._device.get_hw_address()
            ssid = f"SAT_{hw_addr[-5:-3]}{hw_addr[-2:]}"
        
        if passwd is None:
            passwd = "12345678"
        
        logger.info(f"Starting AP mode: SSID={ssid}")

        try:
            import dbus  # type: ignore
            from dbus.exceptions import DBusException  # type: ignore

            bus, devpath, connection_path = self._ensure_hotspot_profile_dbus(
                ssid=ssid,
                passwd=passwd,
                band="bg",
                channel=6,
            )

            nm_proxy = bus.get_object("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager")
            nm = dbus.Interface(nm_proxy, "org.freedesktop.NetworkManager")

            # ActivateConnection(connection, device, specific_object="/")
            acpath = nm.ActivateConnection(connection_path, devpath, "/")
            self._hotspot_active_connection_path = str(acpath)

            if not self._wait_hotspot_activated_dbus(bus, str(acpath), timeout=10):
                raise NotSupportedError("Failed to start access point (timeout waiting for ACTIVATED)")

            logger.info(f"AP started successfully via DBus: {ssid}")

        except DBusException as e:
            # Common in headless/CLI: polkit cannot prompt -> PermissionDenied
            dbus_name = ""
            try:
                dbus_name = e.get_dbus_name() or ""
            except Exception:
                dbus_name = ""

            if dbus_name.endswith(".PermissionDenied") or "PermissionDenied" in str(e):
                self._wifi_mode = "IDLE"
                raise NotSupportedError(
                    "启动热点被 NetworkManager 拒绝授权：Not authorized to share connections via wifi.\n"
                    "这通常需要 polkit 授权（桌面环境会弹窗）或以 root 运行。\n"
                    "如果你是在终端/无图形界面运行，请用 sudo 运行当前程序/命令再试。"
                ) from e

            self._wifi_mode = "IDLE"
            raise NotSupportedError(f"Failed to start AP mode via DBus: {e}") from e
        except Exception as e:
            self._wifi_mode = "IDLE"
            raise NotSupportedError(f"Failed to start AP mode via DBus: {e}") from e

        # Update local state (common for both DBus/libnm paths)
        self._ap_ssid = ssid
        self._ap_passwd = passwd
        self._wifi_mode = "AP"
        return ssid, passwd

    def ap_stop(self) -> None:
        """
        Stop WiFi access point (AP) mode.
        """
        logger.info("Stopping AP mode")
        
        if self._wifi_mode != "AP":
            logger.info(f"Not in AP mode (current: {self._wifi_mode}), skipping")
            return
        
        try:
            import dbus  # type: ignore

            bus = dbus.SystemBus()
            nm_proxy = bus.get_object("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager")
            nm = dbus.Interface(nm_proxy, "org.freedesktop.NetworkManager")
            devpath = nm.GetDeviceByIpIface(self.wifi_iface_name)

            proxy = bus.get_object("org.freedesktop.NetworkManager", devpath)
            device = dbus.Interface(proxy, "org.freedesktop.NetworkManager.Device")
            device.Disconnect()

            time.sleep(1)

            # 重要：按 DBus 示例逻辑，默认不删除 hotspot profile，方便下次复用
            self._hotspot_active_connection_path = None

            self._wifi_mode = "IDLE"
            self._ap_ssid = ""
            self._ap_passwd = ""
            
            logger.info("AP stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping AP: {e}")
            self._wifi_mode = "IDLE"

    def status(self) -> Dict[str, Any]:
        """
        Get current WiFi status.
        
        Returns:
            Dictionary containing current WiFi status information.
        """
        status_dict = {
            "wifi_mode": self._wifi_mode,
            "device_state": str(self._device.get_state().value_nick),
            "hw_address": self._device.get_hw_address(),
        }
        
        if self._wifi_mode == "STA":
            status_dict["sta_conn_wifi_ssid"] = self._sta_conn_wifi_ssid
            status_dict["sta_conn_wifi_passwd"] = self._sta_conn_wifi_passwd
            
            # Get active connection info
            active_conn = self._device.get_active_connection()
            if active_conn:
                ip4_config = active_conn.get_ip4_config()
                if ip4_config:
                    addresses = ip4_config.get_addresses()
                    if addresses:
                        status_dict["sta_status"] = {
                            "ip_address": addresses[0].get_address(),
                            "state": active_conn.get_state().value_nick,
                        }
        
        if self._wifi_mode == "AP":
            status_dict["ap_ssid"] = self._ap_ssid
            status_dict["ap_passwd"] = self._ap_passwd
            
            # Get connected clients from DHCP leases
            status_dict["client_list"] = self._get_ap_clients()
        
        logger.info(f"Status: {status_dict}")
        return status_dict


# Export the backend class
wifi_backend = LinuxWifiBackend
