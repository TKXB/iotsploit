# Verifying the CAN features yourself

Five levels, cheapest first. Each one is useful on its own — you do not need
hardware to check most of this.

## 0. The step everyone trips on

Both plugins are registered as packaged **entry points**, and entry points are
written into installed metadata. Pulling the branch is not enough: until the
package is reinstalled, `list_plugin_info` does not know the plugins exist and
they appear nowhere in the UI or CLI.

```bash
poetry run pip install -e iotsploit-exploits --no-deps --force-reinstall
```

Check it took:

```bash
poetry run python -c "
from importlib.metadata import entry_points
n = sorted(e.name for e in entry_points(group='iotsploit.exploit_plugins'))
print(len(n), 'plugins |', [x for x in n if x.startswith('can_')])"
```

Expect `21 plugins | ['can_frame_composer', 'can_live_capture']`. If you see 19
and an empty list, the reinstall did not happen.

Do this on **every machine** you test on, the Pi included — its
`~/iotsploit-env` needs it too.

## 1. No hardware, no server: run the suites

```bash
tools/testing/test-python-full.sh          # from the repo root
cd ui && tools/testing/test-flutter-full.sh
```

Expect **1025 Python** and **448 Flutter**, zero failures.

If `fvm flutter` fails with "Invalid kernel binary format version", fvm's shim
is running under an older global Dart. Use the pinned SDK directly:

```bash
FLUTTER=~/fvm/versions/3.35.7/bin/flutter \
DART=~/fvm/versions/3.35.7/bin/dart \
tools/testing/test-flutter-full.sh
```

To see only the CAN tests and read what each one asserts:

```bash
poetry run pytest iotsploit-protocols/tests/test_canbus_catalog.py \
                  iotsploit-protocols/tests/test_canbus_codec.py \
                  iotsploit-protocols/tests/test_socketcan_client.py \
                  iotsploit-exploits/tests/test_can_frame_composer.py \
                  iotsploit-exploits/tests/test_can_live_capture.py -v
```

## 2. No hardware: encode a real frame

`vw_golf_mqb` has 113 usable frames on one bus; `zxd_v5` has ~700 across seven,
and is `draft`, which is what exercises the draft-override path.

```bash
poetry run python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iotsploit_django.settings.dev')
django.setup()
from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_exploits.canbus.frame_composer import CanFrameComposerPlugin

target = TargetManager.get_instance().get_target('vw_golf_mqb')
request = {
    'schema_version': 1, 'operation': 'preview',
    'frame': {'bus_id': 'bus_powertrain_can', 'frame_id': 0x462,
              'is_extended': False, 'name': 'PSD_04'},
    'signals': {'PSD_Object_Index': '5'},
    'transport': {'interface': 'socketcan', 'channel': 'can0', 'timeout_ms': 1000},
}
result = CanFrameComposerPlugin().execute(target, {'request': request})
print(result.success, result.data['frame']['data_hex'], result.data['decoded'])
PY
```

Expect `True 0500000000000000 {'PSD_Object_Index': 5}`.

**Things worth breaking on purpose.** Each should fail with a specific message,
not a traceback and not a generic failure:

| Change | Expected |
|---|---|
| `'PSD_Object_Index': '99'` | refused — 99 is outside the documented 0..63 |
| `'name': 'WrongName'` | refused — the target changed since the form was built |
| `'frame_id': 0x999` | refused — does not fit an 11-bit identifier |
| drop the `signals` entry | `field_errors` says that signal is `required` |
| `'operation': 'transmit'`, no digest | refused before any socket is opened |
| `'operation': 'transmit'` + a wrong digest | refused as stale |

That last pair is the safety property: **no digest, no transmit**, and it is
enforced before transport is even imported.

Explore what a target documents:

```bash
poetry run python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iotsploit_django.settings.dev')
django.setup()
from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_protocols.canbus import TargetCanCatalog

catalog = TargetCanCatalog.from_target(
    TargetManager.get_instance().get_target('zxd_v5'))
for bus in catalog.buses:
    bad = [f for f in bus.frames if not f.is_supported]
    print(f'{bus.bus_id:<26} {len(bus.frames):>4} frames, {len(bad)} unusable')
    for frame in bad[:2]:
        print(f'      {frame.frame_id_hex} {frame.name}: {frame.unsupported_reason}')
PY
```

## 3. Hardware, read-only: capture a live bus

Safe on the Pi's `can0`. The interface is already up and already receiving, so
a capture adds no electrical behaviour the bus was not already seeing. **It is
not electrically inert in general, though** — see the note at the end.

```bash
ssh tkxb@10.8.0.10
cd ~/Projects/iotsploit
```

A quick raw sanity check first, so you know the bus is alive:

```bash
timeout 3 candump -n 10 can0
```

Then the real thing, through the plugin. From the **Control Panel** (not the
Plugins page — it has no prompt surface), set `bus_id` and press Execute; the
run asks for the interface, the window, and a confirmation. Interfaces are read
from sysfs, so what you see listed is what the host has.

`duration_s` over 5 routes to the task queue, so keep it short for a
synchronous test. Passing a full `request` object skips every question, which
is what scripted callers do.

Compare what it reports against `candump` running at the same time: frame ids
should match, and the measured periods should look like real cycle times
(10/20/50/100 ms), **not** whatever the definitions declare.

## 4. Hardware, transmitting: use a disposable vcan first

Never rehearse on a live bus. Create a throwaway virtual interface, send
through it, and watch with an independent `candump`:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

candump -td -x vcan0 &          # the witness
# ... run a preview, then a confirmed transmit, with channel "vcan0" ...
sudo ip link delete vcan0       # tear it down when finished
```

What you should see, and why each part matters:

- the bytes `candump` prints match the preview's `data_hex` exactly — the UI
  never computed them, Python did;
- a standard frame prints a 3-digit id, an extended one 8 digits — python-can
  defaults `is_extended_id` to `True`, so this is a real thing to get wrong;
- an FD frame prints its full length (16, 24, …) rather than being truncated
  at 8.

Only after that is a real bus worth considering, and only on a bench.

## 5. The UI

```bash
poetry run iotsploit --runserver     # backend
cd ui && ~/fvm/versions/3.35.7/bin/flutter run -d linux
```

Select a target with CAN buses, then open **CAN Frame Composer** from either
the Plugins page or the Control Panel — both should open the identical dialog,
which is the point of the shared parameter flow.

Worth clicking through:

- search a frame by name, by decimal id, and by hex id;
- pick a frame with a value table and confirm you get a dropdown of labels
  rather than a box wanting a magic number;
- press **Encode only**, then change any field — **Transmit** must grey out
  again immediately;
- on `zxd_v5` (draft), confirm Transmit stays disabled until you tick the
  acknowledgement, separately from the preview succeeding;
- with no CAN device attached, confirm the channel selector explains how to
  bring an interface up instead of showing an empty dropdown.

The capture table has three states worth seeing side by side without any
hardware — open the **Component Showcase** and find *CAN Live Capture*: traffic,
a faulted bus, and a quiet bus.

## One thing that is easy to assume and wrong

A CAN controller in normal mode **acknowledges frames it receives, in
silicon**. Attaching an interface to a live vehicle bus is therefore not
electrically inert, no matter how read-only the software is. If that matters,
set the link listen-only *outside* IoTSploit before attaching. Neither plugin
will do it for you, deliberately.
