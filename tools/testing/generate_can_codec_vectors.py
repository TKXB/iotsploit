#!/usr/bin/env python3
"""Emit golden bit-layout vectors for the Flutter CAN codec.

The UI packs a frame's bytes locally so the composer's readout can change on
every keystroke, but the backend stays the authority on what reaches the wire.
Two encoders for one layout is a real risk, and the answer is evidence: this
script encodes a spread of frames through ``iotsploit_protocols`` -- which is
``cantools`` -- and writes the results as a Dart constant the UI's unit tests
assert against.

The vectors carry raw integers, never physical values. Scaling is a separate
concern with its own hand-written tests; what a golden vector is uniquely good
for is bit placement, where Motorola straddling and multiplexed branches make a
hand-rolled packer look right and be wrong.

Regenerate after any change to the encoder or to the fixture:

    poetry run python tools/testing/generate_can_codec_vectors.py
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from iotsploit_protocols.canbus import decode_frame, encode_frame
from iotsploit_protocols.canbus.catalog import TargetCanCatalog
from iotsploit_protocols.canbus.definitions import FrameDefinition, SignalDefinition

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "conf" / "vw_golf_mqb_target.json"
OUTPUT = REPO / "ui" / "test" / "support" / "can_codec_golden.dart"

#: Frames taken from the fixture, chosen for what each one exercises.
FIXTURE_FRAMES = {
    "ESP_33": "41 signals, 34 single bits, 2 bits owned by nothing",
    "Motor_14": "31 signals across all eight bytes",
    "Licht_Anf_01": "checksum and counter in byte 0, flags above",
}

CASES_PER_FRAME = 4
SEED = 20260826


def synthetic_frames() -> List[FrameDefinition]:
    """Layouts the fixture does not contain but the codec has to survive.

    Motorola straddling, a signed field, a multiplexed frame, an extended id
    and a CAN FD payload are exactly the cases where bit placement is easy to
    get subtly wrong, and none of them appear in the MQB fixture.
    """
    return [
        FrameDefinition(
            bus_id="synthetic",
            frame_id=0x123,
            is_extended=False,
            name="MotorolaMix",
            dlc=8,
            signals=(
                # Starts at the MSB of byte 0 and runs backwards across three
                # bytes: the layout a hand-rolled packer reverses.
                SignalDefinition(name="BigStraddle", start_bit=7, length=20, byte_order="big"),
                SignalDefinition(
                    name="SignedTemp",
                    start_bit=28,
                    length=12,
                    byte_order="big",
                    signed=True,
                ),
                SignalDefinition(name="IntelWord", start_bit=40, length=16, byte_order="little"),
                SignalDefinition(
                    name="SignedByte",
                    start_bit=56,
                    length=8,
                    byte_order="little",
                    signed=True,
                ),
            ),
        ),
        FrameDefinition(
            bus_id="synthetic",
            frame_id=0x1ABCDEF,
            is_extended=True,
            name="MuxDiagnostic",
            dlc=8,
            signals=(
                SignalDefinition(name="Branch", start_bit=0, length=4, multiplexer="M"),
                SignalDefinition(name="Always", start_bit=4, length=4),
                SignalDefinition(
                    name="OnZero",
                    start_bit=8,
                    length=24,
                    multiplexer="m0",
                    multiplexer_signal="Branch",
                ),
                SignalDefinition(
                    name="OnOne",
                    start_bit=15,
                    length=16,
                    byte_order="big",
                    multiplexer="m1",
                    multiplexer_signal="Branch",
                ),
                SignalDefinition(name="Tail", start_bit=32, length=32),
            ),
        ),
        FrameDefinition(
            bus_id="synthetic",
            frame_id=0x321,
            is_extended=False,
            name="FdPayload",
            dlc=12,
            is_fd=True,
            signals=(
                SignalDefinition(name="Head", start_bit=0, length=8),
                SignalDefinition(name="Wide", start_bit=8, length=48),
                SignalDefinition(name="Late", start_bit=71, length=32, byte_order="big"),
            ),
        ),
    ]


def raw_bounds(signal: SignalDefinition) -> Tuple[int, int]:
    """The raw range this signal can hold, narrowed by any authored min/max."""
    if signal.signed:
        low, high = -(2 ** (signal.length - 1)), 2 ** (signal.length - 1) - 1
    else:
        low, high = 0, 2**signal.length - 1

    factor = signal.factor or 1.0
    if signal.minimum is not None and factor > 0:
        low = max(low, -(-int((signal.minimum - signal.offset) / factor) // 1))
    if signal.maximum is not None and factor > 0:
        high = min(high, int((signal.maximum - signal.offset) / factor))
    return (low, high) if low <= high else (0, 0)


def physical(signal: SignalDefinition, raw: int) -> Any:
    """What the encoder wants: a physical value, integral where it can be."""
    value = raw * (signal.factor or 1.0) + (signal.offset or 0.0)
    return int(value) if float(value).is_integer() else value


def active_names(definition: FrameDefinition, branch: Optional[int]) -> List[str]:
    common = [s.name for s in definition.signals if not s.multiplexer_ids]
    if branch is None:
        return common
    return common + [s.name for s in definition.signals if branch in s.multiplexer_ids]


def build_cases(
    definition: FrameDefinition, rng: random.Random
) -> List[Dict[str, Any]]:
    """Encode a handful of value sets and record raw bits against the bytes."""
    switch = next((s for s in definition.signals if s.is_multiplexer), None)
    branches: List[Optional[int]] = [None]
    if switch is not None:
        branches = sorted({i for s in definition.signals for i in s.multiplexer_ids})

    cases: List[Dict[str, Any]] = []
    for index in range(CASES_PER_FRAME):
        branch = branches[index % len(branches)]
        values: Dict[str, Any] = {}
        for name in active_names(definition, branch):
            signal = definition.signal(name)
            if signal is None:
                continue
            if signal.is_multiplexer and branch is not None:
                values[name] = branch
                continue
            low, high = raw_bounds(signal)
            # First case is all-zero: the state every session opens in, and the
            # one a packer that ignores its inputs still gets right.
            values[name] = physical(signal, low if index == 0 else rng.randint(low, high))

        encoded = encode_frame(definition, values)
        read_back = decode_frame(definition, encoded.data)
        if not read_back.ok:
            raise SystemExit(f"{definition.name}: encoded payload did not decode: {read_back.reason}")

        # Raw values are recorded as unsigned bit patterns, which is what the
        # Dart codec packs. The decoder hands back the signed reading of a
        # signed field, and storing that would make the vector describe a
        # different contract than the one under test.
        raw_bits = {}
        for name, value in sorted(read_back.raw_values.items()):
            signal = definition.signal(name)
            width = signal.length if signal else 64
            raw_bits[name] = int(value) & ((1 << width) - 1)

        cases.append(
            {
                "frame": definition.name,
                "raw": raw_bits,
                "data_hex": encoded.data_hex.upper(),
            }
        )
    return cases


def signal_json(signal: SignalDefinition) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": signal.name,
        "start_bit": signal.start_bit,
        "length": signal.length,
        "byte_order": signal.byte_order,
        "signed": signal.signed,
        "factor": signal.factor,
        "offset": signal.offset,
        "unit": signal.unit,
    }
    if signal.minimum is not None:
        out["minimum"] = signal.minimum
    if signal.maximum is not None:
        out["maximum"] = signal.maximum
    if signal.multiplexer:
        out["multiplexer"] = signal.multiplexer
    if signal.choices:
        out["choices"] = {str(k): v for k, v in signal.choices.items()}
    return out


def frame_json(definition: FrameDefinition, note: str) -> Dict[str, Any]:
    return {
        "note": note,
        "name": definition.name,
        "frame_id": definition.frame_id,
        "is_extended": definition.is_extended,
        "is_fd": definition.is_fd,
        "dlc": definition.dlc,
        "signals": [signal_json(s) for s in definition.signals],
    }


def dart_literal(value: Any, indent: int = 0, list_type: str = "Object?") -> str:
    pad = "  " * indent
    if isinstance(value, Mapping):
        if not value:
            return "<String, Object?>{}"
        inner = ",\n".join(
            f"{pad}  {json.dumps(str(k), ensure_ascii=False)}: {dart_literal(v, indent + 1)}"
            for k, v in value.items()
        )
        return "<String, Object?>{\n" + inner + f",\n{pad}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return f"<{list_type}>[]"
        inner = ",\n".join(f"{pad}  {dart_literal(v, indent + 1)}" for v in value)
        return f"<{list_type}>[\n" + inner + f",\n{pad}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def format_dart(path: Path) -> bool:
    """Run the project's formatter over the generated file.

    The Flutter gate runs ``dart format --set-exit-if-changed``, so a generated
    file that is merely valid Dart still fails it. Formatting here keeps
    regeneration from breaking the gate; a missing toolchain is reported rather
    than treated as an error, because generating the vectors is useful without
    one.
    """
    for command in (["fvm", "dart", "format", str(path)], ["dart", "format", str(path)]):
        try:
            result = subprocess.run(
                command, cwd=REPO / "ui", capture_output=True, text=True, timeout=300
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return True
    return False


def main() -> None:
    rng = random.Random(SEED)
    target = json.loads(FIXTURE.read_text())["targets"][0]
    catalog = TargetCanCatalog.from_target(target)

    definitions: List[Tuple[FrameDefinition, str]] = []
    by_name = {
        definition.name: definition
        for bus in catalog.buses
        for definition in bus.frames
    }
    for name, note in FIXTURE_FRAMES.items():
        if name not in by_name:
            raise SystemExit(f"fixture no longer defines {name}")
        definitions.append((by_name[name], f"fixture: {note}"))
    for definition in synthetic_frames():
        definitions.append((definition, "synthetic: a layout the fixture does not contain"))

    frames = [frame_json(d, note) for d, note in definitions]
    cases: List[Dict[str, Any]] = []
    for definition, _ in definitions:
        cases.extend(build_cases(definition, rng))

    body = f'''// GENERATED FILE — DO NOT EDIT BY HAND.
//
// Regenerate with:
//   poetry run python tools/testing/generate_can_codec_vectors.py
//
// Every payload below was produced by the backend encoder in
// `iotsploit_protocols.canbus` (which is `cantools`), from the frame layouts
// in the same file. `can_bit_codec_test.dart` asserts that the Dart codec
// packs the same bytes from the same raw values, which is what keeps the
// composer's live readout honest about what the backend will encode.

/// Frame layouts, in the JSON shape `CanFrameView.fromJson` reads.
const List<Map<String, Object?>> canCodecGoldenFrames =
    {dart_literal(frames, list_type="Map<String, Object?>")};

/// One encoded payload each: frame name, raw signal values, resulting bytes.
const List<Map<String, Object?>> canCodecGoldenCases =
    {dart_literal(cases, list_type="Map<String, Object?>")};
'''

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(body)
    formatted = format_dart(OUTPUT)
    print(
        f"wrote {OUTPUT.relative_to(REPO)}: {len(frames)} frames, {len(cases)} cases"
        f"{'' if formatted else ' (run dart format on it before committing)'}"
    )


if __name__ == "__main__":
    main()
