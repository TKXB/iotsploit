import logging
logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from typing import Optional, Tuple
import netifaces
from iotsploit_django.tools.sat_utils import *
from iotsploit_django.tools.env_mgr import Env_Mgr
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_platforms import get_shared_wifi_backend
from iotsploit_django.tools.net_audit_mgr import NetAudit_Mgr
from iotsploit_django.tools.doip_mgr import DoIP_Mgr
from iotsploit_django.tools.ssh_mgr import SSH_Mgr


@dataclass(frozen=True)
class EcuProfile:
    """Per-ECU configuration. Adding an ECU is a single registry entry below."""
    name: str                               # canonical key, e.g. "tcam"
    display: str                            # label used in every user/log string
    doip_addr: int                         # default DoIP address; the ECU's "doip" facet wins
    static_ip: Optional[str] = None        # fixed IP; when set, skip WiFi/gateway lookup
    ap_ip_env: Optional[str] = None        # env override for the ECU AP-mode IP
    sta_mac_env: Optional[str] = None      # env: expected STA MAC when SAT itself is AP
    ssh_user_env: Optional[str] = None
    ssh_passwd_env: Optional[str] = None
    wifi_ssid_env: Optional[str] = None
    wifi_passwd_env: Optional[str] = None
    supports_wifi: bool = True
    supports_ssh: bool = False
    # Positional layout for vehicle_profile.save_wifi_info(). Each slot is either the
    # token "ssid"/"passwd" or None. Preserves the existing (per-ECU inconsistent)
    # call convention exactly. See _save_wifi_info().
    wifi_save_slots: Tuple[Optional[str], ...] = field(default_factory=tuple)


ECU_REGISTRY = {
    "tcam": EcuProfile(
        name="tcam", display="TCAM",
        doip_addr=DoIP_Mgr.TCAM_Addr,
        ap_ip_env="__SAT_ENV__VehicleModel_TCAM_AP_IP",
        sta_mac_env="__SAT_ENV__VehicleInfo_TCAM_WIFI_STA_MAC",
        ssh_user_env="__SAT_ENV__VehicleModel_TCAM_SSH_USER",
        ssh_passwd_env="__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD",
        wifi_ssid_env="VehicleInfo_TCAM_WIFI_SSID",
        wifi_passwd_env="VehicleInfo_TCAM_WIFI_PASSWD",
        supports_ssh=True,
        wifi_save_slots=("ssid", None, "passwd", None, None, None),
    ),
    "dhu": EcuProfile(
        name="dhu", display="DHU",
        doip_addr=DoIP_Mgr.DHU_Addr,
        ap_ip_env="__SAT_ENV__VehicleModel_DHU_AP_IP",
        sta_mac_env="__SAT_ENV__VehicleInfo_DHU_WIFI_STA_MAC",
        wifi_ssid_env="VehicleInfo_DHU_WIFI_SSID",
        wifi_passwd_env="VehicleInfo_DHU_WIFI_PASSWD",
        wifi_save_slots=(None, None, None, "ssid", None, "passwd"),
    ),
    "vgm": EcuProfile(
        name="vgm", display="VGM",
        doip_addr=0x1001,
        static_ip="169.254.19.1",
        supports_wifi=False,
    ),
}


def doip_address_of(profile: EcuProfile) -> int:
    """The ECU's configured DoIP address, falling back to the registry default.

    The registry entry is no longer the only source: a "doip" facet on the
    matching component overrides it, so a new vehicle variant is a target edit
    rather than a code edit.
    """
    from iotsploit_django.tools.doip_facet import logical_address_for

    return logical_address_for(profile.name, profile.doip_addr)


def _profile(ecu: str) -> EcuProfile:
    p = ECU_REGISTRY.get((ecu or "").lower())
    if p is None:
        raise_err("Unknown ECU: {}, supported: {}".format(ecu, list(ECU_REGISTRY)))
    return p


def _current_target():
    """Return the current domain Target (or None). Lazy import avoids a core<->django cycle."""
    try:
        from iotsploit_django.adapters.django.target_models import TargetManager
        return TargetManager.get_instance().get_current_target()
    except Exception as e:
        logger.debug("No current target available: {}".format(e))
        return None


def check_ecu_alive(ecu: str, checktype: str, allow_live: bool = True) -> bool:
    p = _profile(ecu)
    try:
        if checktype == "ip":
            ip = get_ecu_ip(ecu, allow_live=allow_live)
            return len(NetAudit_Mgr.Instance().ip_detect([ip])) > 0
        return DoIP_Mgr.Instance().check_mcu_alive(doip_address_of(p)) is not False
    except SAT_Exception:
        return False


def get_ecu_ip(ecu: str, allow_live: bool = True):
    """
    Resolve the ECU IP address, target-first.

    Precedence:
      1. Configured IP on the current target's ECU component (durable source of truth).
      2. Registry static_ip (e.g. VGM).
      3. Live derivation from current WiFi/DHCP state (ephemeral, never persisted).

    When ``allow_live`` is False, step 3 is skipped and a SAT_Exception is raised instead —
    used by plugins that must never touch the WiFi subsystem.

    Raise SAT_Exception when none of the above yields an address.
    """
    p = _profile(ecu)

    target = _current_target()
    if target is not None:
        configured = target.get_ecu_ip(ecu)
        if configured:
            logger.info("Using configured {} IP from target: {}".format(p.display, configured))
            return configured

    if p.static_ip is not None:
        return p.static_ip

    if not allow_live:
        raise_err("No IP configured for {} on the current target and live WiFi resolution is "
                  "disabled. Set the {} component's ip_address on the target.".format(p.display, p.display))

    return _resolve_live_ip(ecu)


def _resolve_live_ip(ecu: str):
    """
    Derive the ECU IP from the current WiFi/DHCP state. Ephemeral — not persisted.
    Raise SAT_Exception
    """
    p = _profile(ecu)
    wifi_status = get_shared_wifi_backend().status()
    if wifi_status["wifi_mode"] == "STA":
        if p.ap_ip_env:
            ap_ip = Env_Mgr.Instance().query(p.ap_ip_env)
            if ap_ip != None:
                logger.info("Vehicle model configured {} hotspot LAN IP: {}".format(p.display, ap_ip))
                return ap_ip

        sat_ip = wifi_status.get("sta_status", {}).get("ip_address")
        if sat_ip == None:
            raise_err("SAT failed to obtain an IP address; SAT failed to connect to the {} hotspot!".format(p.display))

        gw_ip = netifaces.gateways()['default'][netifaces.AF_INET][0]
        if gw_ip == None:
            raise_err("SAT failed to obtain the WIFI0 gateway IP address; SAT failed to connect to the {} hotspot!".format(p.display))

        logger.info("SAT connected to the {} hotspot successfully, GW IP: {}".format(p.display, gw_ip))
        return gw_ip

    elif wifi_status["wifi_mode"] == "AP":
        sta_mac = Env_Mgr.Instance().query(p.sta_mac_env) if p.sta_mac_env else None
        if sta_mac != None:
            for client in wifi_status["client_list"]:
                if client["mac"].upper() == sta_mac.upper():
                    logger.info("{} has a STA MAC configured and is connected to the SAT hotspot, {} DHCP INFO: {}".format(p.display, p.display, client))
                    return client["ip"]
            raise_err("{} configured STA MAC: {} but no connection info for {} was found on the SAT hotspot!".format(p.display, sta_mac, p.display))
        else:
            if len(wifi_status["client_list"]) == 0:
                raise_err("{} has no STA MAC configured. No device is connected to the SAT hotspot!".format(p.display))
            else:
                client = wifi_status["client_list"][0]
                logger.info("{} has no STA MAC configured. Selecting the first device on the SAT hotspot as {}: {}".format(p.display, p.display, client))
                return client["ip"]
    else:
        raise_err("SAT network state '{}' does not support querying {} IP".format(wifi_status["wifi_mode"], p.display))


def open_ecu_ssh(ecu: str):
    """
    Open an SSH session to the ECU.
    Raise SAT_Exception

    Return:
    None: connection failed
    ssh_context: connection succeeded
    """
    p = _profile(ecu)
    if not p.supports_ssh:
        raise_err("{} does not support SSH login".format(p.display))

    ecu_ip = get_ecu_ip(ecu)

    ssh_user = Env_Mgr.Instance().get(p.ssh_user_env)
    ssh_passwd = Env_Mgr.Instance().get(p.ssh_passwd_env)
    if ssh_user == None:
        raise_err("Vehicle model has no {} SSH login credentials configured! {} NOT SET!".format(p.display, p.ssh_user_env))

    logger.info("SAT logging into {} SSH IP: {} User: {} -->>".format(p.display, ecu_ip, ssh_user))
    ssh_context = SSH_Mgr.Instance().open_ssh(ecu_ip, ssh_user, ssh_passwd)
    if ssh_context == None:
        raise_err("Vehicle {} SSH login failed. IP: {} User: {}".format(p.display, ecu_ip, ssh_user))

    return ssh_context


def _save_wifi_info(profile: EcuProfile, vehicle_profile, ssid, passwd):
    """Call vehicle_profile.save_wifi_info() using the ECU's positional slot layout,
    preserving the existing per-ECU argument convention."""
    token_map = {"ssid": ssid, "passwd": passwd, None: None}
    args = [token_map[slot] for slot in profile.wifi_save_slots]
    vehicle_profile.save_wifi_info(*args)


def _sta_connect(ssid, passwd):
    """Best-effort STA connect.

    The WiFi backend blocks until the connection activates (or times out) and
    raises on failure; the callers below poll ``status()`` for an assigned IP
    and drive their own retry/UX, so we swallow errors here to preserve that
    flow (matching the old non-raising ``sta_connect_wifi``)."""
    try:
        get_shared_wifi_backend().sta_connect(str(ssid), str(passwd))
    except Exception as e:
        logger.warning("STA connect to '{}' failed: {}".format(ssid, e))


def connect_ecu_wifi(ecu: str):
    p = _profile(ecu)
    if not p.supports_wifi:
        raise_err("{} does not support WiFi hotspot connection".format(p.display))

    cached_ssid = Env_Mgr.Instance().query(p.wifi_ssid_env)
    cached_passwd = Env_Mgr.Instance().query(p.wifi_passwd_env)
    if cached_ssid != None:
        logger.info("SAT cache has {} hotspot info {} {}, auto-connecting".format(p.display, cached_ssid, cached_passwd))
        ssid_list = get_shared_wifi_backend().query_wifi_info_by_ssid(cached_ssid)
        if ssid_list != None and len(ssid_list) != 0:
            _sta_connect(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT waiting for {} hotspot to assign an IP: {}".format(p.display, i))
                sta_status = get_shared_wifi_backend().status().get("sta_status", {})
                if sta_status.get("ip_address") != None:
                    raise_ok("SAT connected to {} device {} hotspot successfully. Connection info: {}".format(p.display, cached_ssid, sta_status))

        user_select = Input_Mgr.Instance().single_choice(
            "{} hotspot connection failed. Please confirm the {} hotspot is on and verify the hotspot info: {} {}".format(p.display, p.display, cached_ssid, cached_passwd),
            ["Hotspot is on, info is correct", "Hotspot is on, info is incorrect, re-enter"])

        if user_select == "Hotspot is on, info is correct":
            logger.info("SAT cache has {} hotspot info {} {}, auto-connecting again".format(p.display, cached_ssid, cached_passwd))
            _sta_connect(cached_ssid, cached_passwd)
            for i in range(30):
                sat_sleep(1)
                logger.info("SAT waiting for {} hotspot to assign an IP: {}".format(p.display, i))
                sta_status = get_shared_wifi_backend().status().get("sta_status", {})
                if sta_status.get("ip_address") != None:
                    raise_ok("SAT connected to the {} hotspot successfully. Connection info: {}".format(p.display, sta_status))
            raise_err("SAT failed to connect to the {} hotspot.".format(p.display))
        else:
            logger.info("Clearing existing {} hotspot info from the SAT cache".format(p.display))
            Env_Mgr.Instance().unset(p.wifi_ssid_env)
            Env_Mgr.Instance().unset(p.wifi_passwd_env)
    else:
        logger.info("SAT cache has no {} hotspot info".format(p.display))
        Input_Mgr.Instance().confirm("Connecting to this vehicle's {} hotspot for the first time; please confirm the {} hotspot is on".format(p.display, p.display))

    cached_ssid = None
    for i in range(5):
        ssid_choice_list = []
        ssid_list = get_shared_wifi_backend().query_wifi_info_by_ssid(None)
        if ssid_list != None and len(ssid_list) != 0:
            for wifi_info in ssid_list:
                ssid_choice_list.append(wifi_info["ssid"])
        ssid_choice_list = list(set(ssid_choice_list))
        ssid_choice_list.append("Rescan hotspots")
        ssid_choice_list.append("Cancel hotspot connection")
        cached_ssid = Input_Mgr.Instance().single_choice(
                    "Please select the WiFi hotspot to connect to",
                    ssid_choice_list)
        if cached_ssid == "Rescan hotspots":
            cached_ssid = None
            continue
        if cached_ssid == "Cancel hotspot connection":
            raise_err("Failed to connect to the {} hotspot; user cancelled the hotspot connection".format(p.display))
        break

    if cached_ssid == None:
        raise_err("Failed to connect to the {} hotspot; user could not find the {} hotspot".format(p.display, p.display))

    cached_passwd = Input_Mgr.Instance().string_input(
                "Please enter the WiFi password for the {} WiFi hotspot: {}".format(p.display, cached_ssid))
    for retry_passwd in range(5):
        _sta_connect(cached_ssid, cached_passwd)
        for i in range(30):
            sat_sleep(1)
            logger.info("SAT waiting for the hotspot to assign an IP: {}".format(i))
            sta_status = get_shared_wifi_backend().status().get("sta_status", {})
            if sta_status.get("ip_address") != None:
                Env_Mgr.Instance().set(p.wifi_ssid_env, cached_ssid)
                Env_Mgr.Instance().set(p.wifi_passwd_env, cached_passwd)
                vehicle_profile = Env_Mgr.Instance().query("VEHICLE_PROFILE")
                if vehicle_profile != None:
                    _save_wifi_info(p, vehicle_profile, cached_ssid, cached_passwd)
                else:
                    logger.error("VEHICLE_PROFILE NOT FOUND In ENV!!")

                raise_ok("SAT connected to the {} hotspot successfully. Connection info: {}".format(p.display, sta_status))

        cached_passwd = Input_Mgr.Instance().string_input(
                "Connection timed out {}. Please re-enter the WiFi password for the {} WiFi hotspot: {}".format(retry_passwd, p.display, cached_ssid))

    raise_err("Failed to connect to the {} hotspot. The {} hotspot info entered by the user: {} {} cannot connect".format(p.display, p.display, cached_ssid, cached_passwd))
