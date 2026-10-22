"""Bus identification refuses silent guesses when definitions overlap."""

from __future__ import annotations

import pytest

from iotsploit_protocols.canbus import TargetCanCatalog
from iotsploit_protocols.canbus.bus_match import score_buses

pytestmark = pytest.mark.unit


def catalog_with(*buses):
    return TargetCanCatalog.from_target(
        {
            "target_id": "bench",
            "name": "Bench",
            "type": "vehicle",
            "buses": [
                {
                    "bus_id": bus_id,
                    "name": bus_id,
                    "type": "can",
                    "properties": {
                        "messages": [
                            {"frame_id": frame_id, "name": f"F{frame_id:X}", "dlc": 1}
                            for frame_id in frame_ids
                        ]
                    },
                }
                for bus_id, frame_ids in buses
            ],
            "components": [],
        }
    )


def test_an_unambiguous_bus_is_reported_as_the_winner():
    catalog = catalog_with(("body", [0x100, 0x101, 0x102]), ("chassis", [0x100]))

    result = score_buses(catalog, {(0x100, False), (0x101, False), (0x102, False)})

    assert result.outcome == "winner"
    assert result.best_bus_id == "body"
    assert result.rows[0].coverage == 1.0


def test_traffic_explained_by_no_bus_is_not_a_low_score_winner():
    catalog = catalog_with(("body", [0x100]), ("chassis", [0x200]))

    result = score_buses(catalog, {(0x700, False)})

    assert result.outcome == "none"
    assert result.best_bus_id is None


@pytest.mark.parametrize("second_score", [9, 10])
def test_a_near_or_exact_tie_says_to_listen_longer(second_score):
    heard = {(frame_id, False) for frame_id in range(10)}
    catalog = catalog_with(
        ("body", list(range(10))),
        ("chassis", list(range(second_score))),
    )

    result = score_buses(catalog, heard)

    assert result.outcome == "tie"
    assert "longer" in result.as_dict()["message"].lower()


def test_an_empty_sample_is_distinct_from_unexplained_traffic():
    result = score_buses(catalog_with(("body", [0x100])), set())

    assert result.outcome == "no_frames"
