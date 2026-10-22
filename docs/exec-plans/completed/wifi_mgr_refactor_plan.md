# WiFi Manager Refactor Plan

Goal: refactor `wifi_mgr.py` into a facade that uses the new multi-platform backend interface while preserving current Linux behavior.

## Architecture (ASCII)

```
             +---------------------------+
             |        Callers/UI         |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             |  wifi_mgr.py (facade)     |
             |  iotsploit-django         |
             +-------------+-------------+
                           |
                           v
             +---------------------------+
             |  WifiBackend (port)       |
             |  iotsploit-core           |
             +-------------+-------------+
                           |
                           v
     +---------------------+---------------------+
     |                                           |
     v                                           v
 +---------------------+              +---------------------+
 | Linux wifi_backend  |              | Windows wifi_backend|
 | iotsploit-platforms |              | iotsploit-platforms |
 +---------------------+              +---------------------+
                 ^
                 |
     +---------------------+
     | Darwin wifi_backend |
     | iotsploit-platforms |
     +---------------------+
```

## Full Plan

1) Baseline behavior and call sites
- Scan the repo for `WiFi_Mgr`, `sta_connect_wifi`, `ap_start`, `query_wifi_info_*`, and `status`.
- Record input/output shapes and any assumptions (return values, exceptions, side effects).

2) Architecture placement
- Keep `iotsploit_core/ports/wifi_backend.py` as the stable interface.
- Create Linux adapter in `iotsploit-platforms/.../linux/wifi_backend.py` with current behavior.
- Keep `iotsploit-django/.../wifi_mgr.py` as a facade only.

3) Linux adapter scope (behavior preserved)
- Move `pywifi` STA logic and `dhclient` calls into `sta_connect`/`sta_disconnect`.
- Move `hostapd`/`dnsmasq`/`iptables`/`systemd-resolved` AP logic into `ap_start`/`ap_stop`.
- Preserve temp paths, hostapd template, default SSID/password rules, and `DeviceInfo` usage.

4) Facade design (backward compatible)
- Keep `WiFi_Mgr` class and `_instance`.
- Map legacy methods to backend:
  - `sta_connect_wifi` -> `sta_connect`
  - `sta_disconnect` -> `sta_disconnect`
  - `ap_start`/`ap_stop` -> corresponding backend methods
  - `status`, `query_wifi_info_by_bssid`, `query_wifi_info_by_ssid` -> backend or default interface methods
- Normalize exceptions: convert unsupported platform to `NotSupportedError`, keep logs.

5) Platform selection and capability reporting
- Select backend based on `iotsploit_core/platforms/consts.py` and optional settings/env.
- Expose capability flags in `status()` or a dedicated method (e.g., `supports_ap`, `supports_sta`, `supports_scan`).

6) Non-Linux minimal adapters
- Implement Windows/macOS adapters with `scan` + `sta_connect` only.
- Raise `NotSupportedError` for AP mode and other unsupported operations.
- Keep return formats consistent with Linux.

7) Call site migration strategy
- Keep legacy method names initially to avoid breaking callers.
- Update call sites incrementally to the new interface after facade is stable.

8) Verification and rollback
- On Linux, compare old/new behavior for `sta_connect`, `ap_start`, and `status` output.
- If regression occurs, revert facade to previous logic and isolate adapter changes.
