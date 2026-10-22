"""The export envelope: what it writes, and what it refuses to read."""

from __future__ import annotations

import pytest

from iotsploit_core.domain.target_transfer import (
    ENVELOPE_KEY,
    EXPORT_VERSION,
    TargetTransferError,
    build_envelope,
    read_envelope,
)


TARGET = {"target_id": "demo_car", "name": "Demo Car", "type": "vehicle"}


def test_round_trip_preserves_targets():
    assert read_envelope(build_envelope([TARGET], source="test")) == [TARGET]


def test_header_names_the_version_that_wrote_it():
    header = build_envelope([TARGET], source="test")[ENVELOPE_KEY]
    assert header["version"] == EXPORT_VERSION
    assert header["source"] == "test"
    assert header["exported_at"]


def test_reads_a_headerless_file():
    """Every exporter wrote one of these before this module existed."""
    assert read_envelope({"targets": [TARGET]}) == [TARGET]


def test_refuses_a_newer_version_by_number():
    """A silent partial read of a newer format is how an import loses data."""
    data = {ENVELOPE_KEY: {"version": EXPORT_VERSION + 1}, "targets": [TARGET]}
    with pytest.raises(TargetTransferError, match=f"version {EXPORT_VERSION + 1}"):
        read_envelope(data)


def test_accepts_an_older_version():
    data = {ENVELOPE_KEY: {"version": EXPORT_VERSION, "source": "x"}, "targets": [TARGET]}
    assert read_envelope(data) == [TARGET]


@pytest.mark.parametrize(
    "data, message",
    [
        ([], "top level"),
        ({"components": []}, "no 'targets' list"),
        ({"targets": {}}, "expected a list"),
        ({"targets": ["not an object"]}, "position 0"),
        ({"targets": [{"name": "no id"}]}, "no target_id"),
        ({ENVELOPE_KEY: "nope", "targets": []}, "not an object"),
        ({ENVELOPE_KEY: {"version": "1"}, "targets": []}, "expected an integer"),
    ],
)
def test_refuses_what_is_not_an_export(data, message):
    with pytest.raises(TargetTransferError, match=message):
        read_envelope(data)


def test_empty_export_is_valid_and_distinct_from_a_wrong_file():
    """The distinction ``data.get("targets", [])`` could not make."""
    assert read_envelope(build_envelope([], source="test")) == []
    with pytest.raises(TargetTransferError):
        read_envelope({"something_else": []})
