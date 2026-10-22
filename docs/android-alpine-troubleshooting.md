# Android Alpine runtime troubleshooting

Observed on 2026-10-22 with Python 3.12 in `/root/iot`.

## Expected behavior

With the required runtime dependencies installed, the backend and software-only
APIs should work even when optional hardware is unavailable. USB, SocketCAN,
J-Link, and Ubertooth features should report why they are unavailable without
breaking unrelated APIs. This is the intended behavior, not a claim that this
deployment has passed Android Alpine acceptance testing.

Android hardware access also depends on the host kernel, permissions, and device
access exposed to Alpine. Installing userspace packages does not guarantee USB
or CAN access.

## Findings from the logs and repository

| Message | Classification | Action |
| --- | --- | --- |
| `No time zone found with key Asia/Shanghai` | Missing environment dependency | Install `tzdata`. Django uses this timezone and fails again while rendering other exceptions, producing the repeated traceback. |
| PyUSB `No backend available` | Missing or undiscoverable native dependency | Install `libusb`; verify Python can discover the backend. This differs from finding no attached USB devices. |
| Driver-list API crashes in USB Explorer parameter discovery | Code issue exposed by the missing USB backend | Optional dependency failure should be reported by the owning driver without crashing the driver-list API. This remains unresolved in the inspected source. |
| BusyBox `ip` prints usage during CAN scans | Tool incompatibility | Install `iproute2`. CAN discovery requires `ip -details link show`. |
| `TargetManager` has no attribute `Session` | Application initialization bug | The checkout contains fix `ac383553` (`fix(targets): never hand out a half-built TargetManager`). Update the deployed Django package; do not hide the bug by catching `AttributeError`. |
| Repeated `/api/health/` HTTP 404 | Deployment/version or URL configuration mismatch | The checkout exposes this route, added in `7d29c191`. Update the installed backend and verify the process uses the intended environment and URL configuration. |
| Missing J-Link SDK or Ubertooth tools | Optional dependency warnings | Install only if those features are needed; warnings and skipped scans are appropriate. |
| No ESP32 or logic analyzer found | Expected when no accessible matching device exists | Check hardware access only if the device should be present. |
| Missing `usb_devices.json` | Configuration/path issue | Verify the deployed USB configuration path and packaged configuration. It is not evidence that USB hardware is absent. |
| DoIP facet re-registration | Duplicate registration in project code | Consolidate registration at its owner; unrelated to Alpine. |
| ECP5 FPGA discovered and connected | Hardcoded demonstration behavior | The inspected driver returns a predefined device and simulates connection; these logs do not prove real FPGA access. |
| Daphne HTTP/2 support not enabled | Informational | Normal HTTP/WebSocket operation does not require enabling HTTP/2. |

Server startup succeeds in the supplied logs. The initialization endpoint's HTTP
200 confirms that the request completed, not that every driver initialized.
The first application failures are the missing `TargetManager.Session` and USB
backend errors; the missing timezone data then obscures them during error
rendering. Installing timezone data alone will not resolve those original errors.

## Phone recovery steps

1. Install the Alpine system dependencies:

   ```sh
   apk add --no-cache tzdata iproute2 libusb
   ```

2. If PyUSB still cannot discover libusb, follow its Alpine guidance and install
   `gcc` and `libusb-dev`, then check backend discovery again.
3. Update/reinstall the installed `iotsploit-*` packages together from the same
   intended project revision, using the project's Poetry workflow. In particular,
   ensure `iotsploit-django` includes the TargetManager fix and health endpoint.
   Updating a source checkout alone does not necessarily update packages under
   `/root/iot/lib/python3.12/site-packages/`.
4. Stop and restart IoTSploit using the updated environment.
5. Confirm `/api/health/` returns HTTP 200 for a healthy runtime, target listing
   works, and driver listing no longer returns HTTP 500. Investigate any failing
   health checks or remaining original exceptions separately.

Expected dependency failures should be handled at their feature owner with a
clear unavailable reason. Unexpected initialization bugs should be fixed at the
source rather than converted into empty results or false success.

## References

- [Python timezone data sources](https://docs.python.org/3.12/library/zoneinfo.html#data-sources)
- [PyUSB FAQ, including Alpine backend discovery](https://github.com/pyusb/pyusb/blob/master/docs/faq.rst)
- [Alpine iproute2 package](https://pkgs.alpinelinux.org/package/v3.20/main/aarch64/iproute2)

This document records diagnosis and recovery guidance. It does not implement the
remaining code fixes or record a successful retest on the phone.
