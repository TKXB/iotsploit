"""Explicit cross-repository parser agreement gate; requires ui/ and Cargo.

Run with: poetry run pytest tools/testing/test_network_descriptions.py
The standalone inspect example uses the exact native document owner as Flutter.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import cantools
import pytest

from iotsploit_django.tools.dbc import parse_dbc

ROOT = Path(__file__).resolve().parents[2]
CAN = ROOT / "ui/can"
SAMPLES = CAN / "fixtures/network-descriptions"


@pytest.fixture(scope="module")
def inspect_native():
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(CAN / "Cargo.toml"),
         "-p", "network-description", "--example", "inspect"],
        check=True, capture_output=True, text=True,
    )

    def inspect(filename):
        result = subprocess.run(
            [str(CAN / "target/debug/examples/inspect"), str(SAMPLES / filename)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)

    return inspect


@pytest.mark.parametrize("filename", ["motohawk.dbc", "multiplex.dbc"])
def test_dbc_common_subset_agrees_with_live_python_parser(inspect_native, filename):
    native = inspect_native(filename)
    legacy = parse_dbc((SAMPLES / filename).read_text())
    details = native["details"]
    expected_nodes = {node.name for node in legacy.nodes}
    assert {d["entry"]["name"] for d in details if d["entry"]["category"] == "Nodes"} == expected_nodes
    expected = [(node.name, frame) for node in legacy.nodes for frame in node.messages]
    expected += [("Unspecified", frame) for frame in legacy.unsent]
    frames = [d for d in details if d["entry"]["category"] == "Frames"]
    assert len(frames) == len(expected)
    for sender, frame in expected:
        actual = next(d for d in frames if d["entry"]["name"] == frame.name)
        assert actual["properties"] == {
            "Identifier": f"0x{frame.frame_id:X}", "Extended": frame.is_extended,
            "Payload bytes": frame.dlc, "Transmitter": sender,
        }
        signals = [d for d in details if d["entry"]["parent"] == actual["entry"]["id"]]
        assert len(signals) == len(frame.signals)
        for signal in frame.signals:
            properties = next(d["properties"] for d in signals if d["entry"]["name"] == signal.name)
            assert properties == {
                "Start bit": signal.start_bit, "Length (bits)": signal.length,
                "Byte order": "Big" if signal.byte_order == "big" else "Little",
                "Signed": signal.signed, "Factor": signal.factor, "Offset": signal.offset,
                "Minimum": signal.minimum, "Maximum": signal.maximum, "Unit": signal.unit,
                "Multiplexer": signal.multiplexer,
                "Choices": {str(key): value for key, value in (signal.choices or {}).items()},
            }


def test_arxml_frame_occurrences_and_lengths_agree_with_cantools(inspect_native):
    native = inspect_native("system-4.2.arxml")
    database = cantools.database.load_file(str(SAMPLES / "system-4.2.arxml"), strict=True)
    details = native["details"]
    by_id = {d["entry"]["id"]: d for d in details}
    triggerings = [d for d in details if d["entry"]["kind"] == "CAN-FRAME-TRIGGERING"]
    assert len(triggerings) == len(database.messages) == 8
    for triggering in triggerings:
        frame_link = next(r for r in triggering["references"] if "FRAME-REF" in r["field"])
        frame = by_id[frame_link["target"]]
        expected = next(m for m in database.messages if m.name == frame["entry"]["name"])
        identifier = next(v for k, v in triggering["properties"].items() if "/IDENTIFIER[" in k)
        length = next(v for k, v in frame["properties"].items() if "/FRAME-LENGTH[" in k)
        assert int(identifier) == expected.frame_id
        assert int(length) == expected.length
    # The viewer preserves source definitions/placements; its Signals count is
    # intentionally not cantools' flattened per-message signal count.
