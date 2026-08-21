# Linux WiFi Backend Refactor Plan

Goal: make `iotsploit_platforms.adapters.platforms.linux.wifi_backend` safe, predictable, and distro-tolerant while preserving current behavior.

## Plan

1) Remove unsafe constructor side effects
- Stop calling `_init_wifi_proxy()` from `__init__`.
- Make `_init_wifi_proxy()` purely internal and only run when needed.
- Ensure `ap_stop()`/`sta_disconnect()` are not called implicitly on init.

2) Add capability checks and error reporting
- Add a lightweight command availability check (`hostapd`, `dnsmasq`, `wpa_cli`, `dhclient`, `iptables`, `ifconfig`).
- If required tools are missing, raise `NotSupportedError` with actionable messages.
- Capture `subprocess.run` return codes and raise on failures.

3) Make AP teardown safe
- Track whether AP was started by this backend (boolean flag).
- Only stop `hostapd/dnsmasq`, flush NAT, and toggle `ip_forward` if AP was started.
- Guard `iptables -t nat -F` so it doesn’t wipe unrelated rules.

4) Harden interface access
- Validate `wifi_iface_name` exists before use.
- Handle missing/empty `netifaces` results when generating default SSID.
- Fail early with clear errors instead of stack traces.

5) Replace legacy tools where possible
- Prefer `ip` over `ifconfig` if available.
- Prefer `systemctl` for `systemd-resolved` if present; otherwise skip service toggle.
- Keep fallbacks but log what’s used.

6) Reduce global system impact
- Avoid unconditional `killall dhclient`; target the PID file you spawned.
- Consider using `iptables` rules with comments or a dedicated chain so cleanup is scoped.

7) Add structured status and capability output
- Return a stable `status()` shape.
- Add `supports_ap`, `supports_sta`, `supports_scan` fields for UI.

8) Verification checklist
- Test STA connect/disconnect on Linux with and without existing dhclient.
- Test AP start/stop and ensure iptables changes are scoped and restored.
- Test behavior when required tools are missing (should raise cleanly).
