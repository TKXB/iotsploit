# CAN Live Capture

Watch a CAN bus for a bounded window and see decoded signal values from the
active target's own definitions, instead of raw hex. What the capture saw is
recorded as observations.

## Safety first, because this one is easy to get wrong

The capture **transmits nothing**. There is no send path in it, not even a
disabled one.

That is not the same as being electrically inert. **A CAN controller in normal
mode acknowledges frames it receives, at the hardware level.** Attaching an
interface to a live vehicle bus therefore changes what is on the wire,
regardless of what this software does or does not send.

If that matters for what you are doing, configure the link listen-only
*outside* IoTSploit before you attach:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on
sudo ip link set can0 up
```

This plugin will not set that for you, for the same reason the composer will
not set a bitrate. The UI shows whether the selected interface is a virtual
`vcan` before a capture starts.

## What a capture produces

```text
Target:  Bench Vehicle          Bus: Powertrain CAN          Channel: can0
Capturing 30s · 4210 frames · 47 ids · 3 undocumented      [Stop]

ID     Name             Count  Period    Last decoded
0x123  VehicleStatus     2981   10ms     VehicleSpeed 42.5 km/h · IgnitionState On
0x2A1  BrakeStatus        598   50ms     BrakePressure 0.0 bar · AliveCounter 7
0x0C4  —                  312   100ms    no definition on this bus
0x3F0  TransmissionData   119   250ms    decode failed: payload 6 bytes, DLC 8
```

Rows are per frame identity, not per frame received. A scrolling log of every
frame on a busy bus is unreadable and would flood the socket, so the stream
carries periodic snapshots of the changed rows.

Rows stay ordered by identity rather than by count, so a frame you are watching
does not move when a busier one overtakes it.

### Periods are measured

`period_ms` comes from observed arrival times, never from the definition's
declared cycle time. Reporting a declaration as though it had been measured is
how a capture stops being evidence.

### Undocumented frames are shown

A frame nobody documented is the finding, not noise to discard. It is counted
with `known: false` and never decoded.

## Bus health is not traffic

A SocketCAN socket delivers **error frames** alongside data frames, and
python-can enables them by default. They are not messages: the ERR flag lives
in the CAN ID, and once python-can masks it off, what remains in
`arbitration_id` is an *error class*, not an address. `CAN_ERR_CRTL` presents
as arbitration id `0x004` with the controller status in `data[1]`.

Anything that reads identity without checking `is_error_frame` first invents a
frame `0x004` that no ECU ever sent. This capture classifies before it reads
identity, so faults never reach the frame table or an observation. They go to a
separate bus-health tally shown above the table.

**Read that tally.** On real hardware it is often the most valuable thing on
screen. A capture reporting zero frames on a healthy link and a capture
reporting zero frames on an error-passive controller look alike and mean
entirely different things — the second is telling you the bitrate is wrong, the
FD configuration is wrong, or the wiring is wrong, which is the actual
explanation for a capture that "sees nothing".

Remote frames are counted as their own category, not as zero-length data
frames.

## Observations

One batch per captured bus, with the bus in the scope key so two buses captured
separately never overwrite each other's history.

Facts use the shape the explorer already renders: `protocol="can"`,
`subject_kind="message"`, `subject_id` the canonical frame id,
`observed_property="seen"`, and a value carrying `name`, `count`, `period_ms`,
`dlc`, plus `known` and `decode_errors`.

### Batches are never marked complete

Deliberately, and this matters. A complete batch is how the observation model
says "this is the whole population now", and it clears prior state. A
thirty-second window cannot say that: a frame on a sixty-second cycle is absent
from the window without being absent from the vehicle, and marking the batch
complete would record it as having disappeared.

Captures therefore accumulate as history and never retract an earlier finding.

`tools/seed_can_observations.py` produced exactly this fact shape while no
sniffer existed. It is now a fixture generator rather than a stand-in.

## Starting one

The run **asks**. Set `bus_id` to the bus you want and press Execute; it then
prompts for the interface, the window, and a confirmation:

```text
Which SocketCAN interface?        can0 (hardware, up)
Capture for how many seconds?     30
Stop after how many frames?       200000
Capture CAN bus 1 on can0 for 30s?
   This transmits nothing. Note though that a CAN controller in normal mode
   acknowledges frames in silicon, so attaching to a live vehicle bus is not
   electrically inert...
```

Interfaces come from sysfs, so the list is what the host actually has —
including ones that are **down**, labelled as such rather than hidden. A
virtual `vcan` is named as one, and its confirmation says plainly that nothing
on it can reach a vehicle.

Prompts need somewhere to be answered: use the **Control Panel** or the
`iotsploit` shell. The Plugins page has no prompt surface and will redirect you.

`bus_id` is an ordinary parameter rather than a question, deliberately. Scan
scopes are declared before the run and the scope key names the bus, so a bus
chosen mid-conversation would arrive too late for its own observations to be
recorded. Getting it wrong is cheap — the error lists the bus ids the target
actually has.

## Request (scripted callers)

Passing a full `request` skips every question. This is the API, MCP, and
CLI-JSON path, and it is unchanged:

```json
{
  "schema_version": 1,
  "bus_id": "bus_can_powertrain",
  "transport": {"interface": "socketcan", "channel": "can0"},
  "duration_s": 30,
  "max_frames": 200000,
  "snapshot_interval_ms": 200,
  "decode": true
}
```

Every capture is bounded by a duration **and** a frame budget, whichever ends
first. Neither is redundant: the frame budget saves you on a busy bus where
thirty seconds is millions of frames, the duration saves you on a silent bus
where the frame budget would never be reached.

`duration_s` over 5 routes the run to the task queue, which is where a capture
belongs.

## Limitations

- Conflicted definitions are counted but never decoded: two documents disagree
  about what the bytes mean, and publishing one reading would publish a guess.
- The number of distinct *undocumented* identities retained is capped. On
  overflow the result says so rather than growing without bound on a fuzzed or
  noisy bus.
- No ISO-TP reassembly, no UDS-over-CAN decoding.
- Capture files are not read or written. Decoding a stored candump/BLF/ASC is a
  separate feature that would reuse the same codec.
- The capture does not diff what it saw against the catalogue or propose target
  edits.

## The raw CAN screen is unchanged

`can_screen.dart` over the `drv_socketcan` driver still shows raw frames and
still works with **no target selected**. That is why it stays: it is the
fallback when there is no target, no definitions, or no decoding wanted. This
feature is a second view beside it, not a replacement.
