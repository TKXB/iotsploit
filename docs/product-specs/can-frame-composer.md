# CAN Frame Composer

Compose one CAN frame from a target's own signal definitions, see the exact
bytes it encodes to, and optionally put that frame on a bus.

## What it is, and what it is not

It is a **one-frame composer**. One request encodes one frame and, if you
confirm, sends it exactly once. It is not a replay tool, not a flooder, not a
cyclic transmitter, and it has no repeat count.

It does **not** transmit arbitrary bytes. Every payload is built from signals
the target documents. The existing raw CAN screen over the `drv_socketcan`
device driver still exists and still sends raw `id` + `data` unconfirmed —
nothing here removes that, so do not describe IoTSploit as making raw
transmission impossible.

## Before you start

The interface must already be up. IoTSploit never runs `sudo`, never calls
`ip link`, and never sets a bitrate, listen-only mode, or FD timing. A tool
that quietly reconfigures a bus to make its own call succeed has changed the
vehicle to suit itself.

Bring one up outside IoTSploit:

```bash
# real hardware
sudo ip link set can0 up type can bitrate 500000

# CAN FD
sudo ip link set can0 up type can bitrate 500000 dbitrate 2000000 fd on

# a disposable virtual bus for practice — sends nothing to any vehicle
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

If the interface is missing or down, the composer says so and names the
channel. It does not try to fix it.

## Using it

1. Select a target. The composer runs against that target's definitions, so it
   will not open without one.
2. Open **CAN Frame Composer** from the Plugins page or the Control Panel.
   Both use the same implementation.
3. Choose the CAN bus, then the frame. Search matches the frame name, its
   decimal id, and its hex id.
4. Choose the SocketCAN interface from the scanned CAN devices. This is the
   kernel interface name (`can0`), not the driver's device id (`can_001`).
5. Enter every active signal. Values are **physical** — `42.5` km/h, not the
   raw integer. Named values are picked by label.
6. Press **Encode only**. The payload shown is computed by Python from the
   target's definitions, not by the UI.
7. Press **Transmit one frame** and confirm.

### Multiplexed frames

Enter the multiplexer first: which signals the frame even contains depends on
its value. Changing it discards values belonging to a branch that is no longer
selected, and says so.

### Nothing is defaulted

Every active signal is required. No field is filled with zero, a minimum, or an
inferred value. A frame sent with an unstated field quietly filled in is not
the frame you composed, and on a live bus that distinction is the whole point.

## What "sent" means

A successful transmit means **the local SocketCAN socket accepted the frame**.
It does not mean an ECU received it, acted on it, or that anything was
listening at all. Nothing in this feature can tell you that, and the result
wording is deliberate.

Also worth knowing: a CAN controller in normal mode acknowledges frames it
receives, in silicon. Attaching an interface to a live bus is not electrically
inert whatever the software does.

## The preview digest

Transmitting requires the digest that a preview of *exactly that request*
returned. The digest covers the target and its status, the bus, the frame
identity and its full encoding-relevant definition, the normalized signal
values, the encoded bytes and flags, and the physical channel.

Its purpose is narrow and worth stating plainly: it catches the target changing
between preview and send — a signal rescaled, a DLC corrected, a re-import.
When that happens the send is refused rather than putting different bytes on
the wire than you approved.

It is **not** authorization, **not** a one-time token, and repeating a
confirmed API call sends another frame. Authentication and rate limiting are
platform-wide gaps this feature does not fill.

## Direct API and MCP

```json
POST /api/execute_plugin/
{
  "plugin_name": "CAN Frame Composer",
  "target_id": "bench_vehicle",
  "parameters": {
    "request": {
      "schema_version": 1,
      "operation": "preview",
      "frame": {
        "bus_id": "bus_can_powertrain",
        "frame_id": 291,
        "is_extended": false,
        "name": "VehicleStatus"
      },
      "signals": {
        "VehicleSpeed": "42.5",
        "IgnitionState": "On",
        "AliveCounter": "3"
      },
      "transport": {
        "interface": "socketcan",
        "channel": "can0",
        "timeout_ms": 1000
      },
      "allow_draft_target": false
    }
  }
}
```

Transmit is the same request with `"operation": "transmit"` and
`"preview_digest"` set to the value the preview returned.

`target_id` is optional but strongly preferred. Without it the backend acts on
the process-global current target, which another client can change between you
building a request and sending it.

Send numbers as **strings**. A 64-bit value routed through a JSON number is
rounded before Python ever sees it.

The MCP `execute_plugin` tool takes the same optional `target_id`.

### CLI

The CLI renders an unknown parameter type as a text field, so pass the same
object as JSON text. It is the same schema, not a second contract.

## Error messages

The composer distinguishes these rather than collapsing them into "CAN send
failed":

| Message | What to do |
|---|---|
| target has no CAN bus … | the bus id is wrong, or the target changed |
| bus … documents no standard frame 0x… | the frame is not on that bus |
| … has conflicting definitions | two documents disagree; fix the target |
| … is a container frame | AUTOSAR container composition is not supported |
| frame … is *X*, not *Y* | the target changed since the form was built |
| signal *N*: required / not a number / not one of … | fix that value |
| the target or the request changed since previewed | preview again |
| target is *draft*, not active | acknowledge explicitly, or fix the target |
| cannot open SocketCAN interface … | bring the interface up outside IoTSploit |

## Limitations

- No checksum, CRC, rolling counter, freshness, or SecOC generation. If those
  are ordinary documented signals you supply them; if an algorithm is required,
  preview fails.
- AUTOSAR container frames are refused.
- No ISO-TP segmentation or UDS-over-CAN.
- No cyclic or repeated send.
- Frames whose definitions conflict cannot be sent until the target is fixed.

## A note on older targets

Component-owned CAN frames imported **before** the facet models were widened
lost their value tables at import time — the stored model dropped unknown keys
on load. `extra="allow"` stops the loss going forward but cannot recover what
was never written. Re-import those targets if a component frame's named values
are missing.
