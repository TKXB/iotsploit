# Firmware fuzz gate transports

`firmware_fuzz_gate.py` uses the own mutation engine, seed execution, retained
JSONL replay, identity checks, resource leases, and per-case boot observation for
both USBTMC and SCPI TCP. Existing targets default to USBTMC. TCP targets declare
`"transport": "tcp"`; their rig entry supplies `"tcp": {"host": "10.42.0.125",
"port": 5025}` and an optional `serial` to match the third `*IDN?` field.
The firmware manifest, programmer, programmer_resource, and flasher options are
identical for either transport. The controller must already reach the board's
network. Credentials are not stored in rig files.

TCP reads are newline framed, bounded to 8192 bytes, with a 3-second I/O timeout
and 10-second case deadline. `clear` and `reconnect` close the session, discard
buffered responses, and allow 100 ms for the single-client listener to process
FIN. They do not send USBTMC control requests. Writes preserve bytes exactly.
Supported scaffold operations are `write_message`, `request_read`, `delay`,
`clear`, `reconnect`, and `canary`; reads may assert `response_regex`. Binary
response blocks and raw USBTMC operations are not supported by this TCP harness.
The canary requires unchanged identity; boot monitoring requires unchanged boot
token. Failures stop the campaign and retain payload and transport evidence.

The `esp32s3-hid` target uses harmless REM uploads and delayed runs. Its retained
cases cover immediate STOP, disconnect cancellation, and partial-upload ownership.
Run explicitly on the physical rig, supplying exact candidate hashes:

```sh
poetry run python tools/hardware/firmware_fuzz_gate.py \
  --target esp32s3-hid --rig /path/to/rigs.json \
  --manifest /path/to/candidate-manifest.json \
  --ui-root /path/to/ui --firmware-root /path/to/iotsploit-usb \
  --flash --flasher /path/to/firmware-flasher \
  --replay conf/fuzz/regressions/esp32s3-hid.jsonl \
  --iterations 64 --seed 47 --output /path/to/evidence
```

A passing result records verified image hashes, source fingerprints, successful
replay and mutation counts, and final boot continuity. Exit 1 means failure;
exit 2 means incomplete validation. Neither permits a firmware commit.
