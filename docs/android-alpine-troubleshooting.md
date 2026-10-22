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
| PyUSB `No backend available` | Backend unavailable; confirmed USB filesystem access failure on this phone | Python finds and loads libusb, but libusb initialization reports `could not find usbfs`. Installing more packages does not resolve this confirmed failure. See the ADB findings below. |
| Driver-list API crashes in USB Explorer parameter discovery | Code issue exposed by the unavailable USB backend | The fix checks PyUSB backend availability and returns static parameter declarations for unavailable drivers. See implementation and validation below. |
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

## Verified ADB findings after package installation

Read-only diagnostics on the connected phone confirmed:

- Alpine runs in a rooted chroot at `/data/local/tmp/alpine`; its launcher binds
  Android's `/dev` and `/sys` into the chroot.
- `libusb`, `libusb-dev`, and `gcc` are installed.
- With the application's PATH, Python's `ctypes.util.find_library("usb-1.0")`
  returns `libusb-1.0.so`. Direct loading of
  `/usr/lib/libusb-1.0.so.0` also succeeds.
- With `PYUSB_DEBUG=debug LIBUSB_DEBUG=4`, libusb 1.0.27 initialization reports
  `could not find usbfs`, followed by `USBError: Other error`. PyUSB ultimately
  exposes this initialization failure as `NoBackendError`.
- `/dev/bus/usb` is absent on Android and inside Alpine. Android's
  `/sys/bus/usb/devices` directory has no entries.
- The inspected USB role reports `device`; `sys.usb.config` reports `adb`.

The remaining USB failure is therefore host/device access, not library discovery
or a missing libusb package. USB hardware use requires an appropriate host/OTG
setup with device nodes accessible to Alpine. That setup has not been tested;
the observations do not establish whether the phone supports every needed USB
feature. No USB role or mount configuration was changed during diagnosis.

The application should report USB features as unavailable in this state while
keeping unrelated APIs usable. The original USB Explorer parameter enumeration
let the backend failure escape and crash driver listing.

## Implementation and validation

The fix extends the existing capability resolver with
`backend:pyusb`. It uses PyUSB's normal backend selection without consuming the
device iterator, so it supports PyUSB's alternative backends and does not require
an attached device. USB Explorer, FT2232, GreatFET, and Ubertooth declare this
requirement. Unavailable drivers return their static command parameter schema
through the device manager instead of triggering live parameter enumeration.
The existing availability response carries the failure reason and diagnostic
hint; the existing lifecycle gate prevents executing unavailable drivers.

A targeted patch was applied to the phone's installed packages, with originals
saved under `/root/iot/usb-fix-backup-20261022-021654`. A temporary Daphne instance
on port 18888 returned HTTP 200 for driver listing, driver states, and
current-target APIs. USB Explorer retained its parameter schema with empty device
options, and USB-dependent drivers reported unavailable. These checks passed
again after applying the final backend-selection refinement. Each test instance
was stopped afterward. The original backend was not restarted during these
diagnostics; the user subsequently confirmed the fix works on the phone.

Local full-gate results after the final backend-selection refinement: **2032
passed, 2 failed, 5 skipped, 47 warnings**. The same two failures reproduce on
unchanged `dev` (**2027 passed, 2 failed, 5 skipped, 47 warnings**):

- `test_container_resolves_the_real_jlink_driver_for_segger_probes`: expected
  `usb_status` monitor kind is absent.
- `test_text_that_is_not_json_is_refused_without_reaching_a_handler`: deeply
  nested JSON is decoded and rejected as a list, rather than failing decoding
  with the expected error text.

The full phone test gate ran in a separate source checkout and copied virtual
environment at `/root/iotsploit-phone-tests`, using Poetry to install the current
packages and test dependencies. The stale root lock file was regenerated only
in that isolated checkout. Alpine build prerequisites were installed to compile
the ARM64 dependencies; test Python dependency installation did not target the
running `/root/iot` environment.

The first phone run had **2032 passed, 1 failed, 6 skipped, 47 warnings**. Five
skips needed Redis; one needed the optional Radamsa binary. To execute every
case, Redis was provisioned on isolated port 16379 with persistence disabled,
and Radamsa 0.7 was compiled for ARM64 into the test virtual environment using
the upstream release's generated C source.

The final full phone gate completed with **2038 passed, 1 failed, zero skipped,
47 warnings** in 64.10 seconds. Ruff, import smoke, and portability checks passed.
All USB regression cases passed. The one failure is the same nested-JSON
assertion reproduced on unchanged local `dev`; the monitor-kind test passes
with the freshly installed phone package metadata. No tests were weakened or
excluded. The temporary Redis instance was stopped after the run.

Phone evidence:

- `/tmp/iotsploit-phone-full-gate.log`: final complete gate output.
- `/tmp/iotsploit-phone-full-gate-initial.log`: initial run with six skips.
- `/tmp/iotsploit-usb-fix-phone-final-api.log`: final temporary backend log.

The full gate remains red on the failures described above. After reviewing the
results and confirming the phone works, the user requested a pull request
targeting `dev` with those validation limits recorded.

## Phone recovery steps

1. Install the Alpine system dependencies:

   ```sh
   apk add --no-cache tzdata iproute2 libusb
   ```

2. If PyUSB cannot discover libusb, follow its Alpine guidance and install `gcc`
   and `libusb-dev`. These are already installed on the inspected phone. If the
   library loads but initialization fails, inspect `PYUSB_DEBUG=debug
   LIBUSB_DEBUG=4` output instead of assuming another package is missing. The
   confirmed `could not find usbfs` failure requires USB access or graceful
   feature unavailability, not another package installation.
3. Update/reinstall the installed `iotsploit-*` packages together from the same
   intended project revision, using the project's Poetry workflow. In particular,
   ensure `iotsploit-django` includes the TargetManager fix and health endpoint.
   Updating a source checkout alone does not necessarily update packages under
   `/root/iot/lib/python3.12/site-packages/`.
4. Stop and restart IoTSploit using the updated environment.
5. Confirm `/api/health/` returns HTTP 200 for a healthy runtime and target listing
   works. Driver listing must also stop returning HTTP 500, which requires fixing
   USB Explorer's handling of an unavailable backend if USB access remains absent.
   Investigate any failing health checks or remaining original exceptions
   separately; a package update alone is not evidence that this code fix exists.

Expected dependency failures should be handled at their feature owner with a
clear unavailable reason. Unexpected initialization bugs should be fixed at the
source rather than converted into empty results or false success.

## References

- [Python timezone data sources](https://docs.python.org/3.12/library/zoneinfo.html#data-sources)
- [PyUSB FAQ, including Alpine backend discovery](https://github.com/pyusb/pyusb/blob/master/docs/faq.rst)
- [Alpine iproute2 package](https://pkgs.alpinelinux.org/package/v3.20/main/aarch64/iproute2)
- [Radamsa upstream release and generated C source](https://gitlab.com/akihe/radamsa/-/releases)

This document records diagnosis, recovery guidance, and the USB
fix's validation. Other findings in the table remain outside this fix; a full
application acceptance retest has not been completed.
