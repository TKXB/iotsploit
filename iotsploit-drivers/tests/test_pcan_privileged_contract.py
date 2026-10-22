"""The PCAN driver's bit timing must be a request the root daemon accepts.

`FD_TIMING` is the one thing in the driver that no unit test can be wrong
about safely: it is copied verbatim into a `can-fd-up` request, and the daemon
that receives it validates every field and refuses anything it does not
recognise. A renamed key or an out-of-range sample point is a driver that
raises no link at all, and the only place that used to show up was on a bench
with an adapter plugged in.

This closes the half of that gap which is software: the driver's constant
travels through the daemon's real validator and comes out as the exact `ip`
argv an operator would type. The other half -- whether a PEAK controller
accepts this timing against its own clock and tseg ranges -- is a property of
silicon and stays a manual bench check.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

if sys.platform != "linux":
    pytest.skip("the privileged daemon is Linux-only", allow_module_level=True)

from iotsploit_drivers.socketcan.drv_pcan import FD_TIMING  # noqa: E402

pytestmark = pytest.mark.contract

DAEMON_PATH = Path(__file__).resolve().parents[2] / "iotsploit-priv" / "privd" / "iotsploit-privd"
DAEMON = runpy.run_path(str(DAEMON_PATH))


def validate(verb: str, args: dict):
    function = DAEMON["_validate_request"]
    function.__globals__["IP_EXECUTABLE"] = "/usr/sbin/ip"
    return function({"verb": verb, "args": args})


def test_the_drivers_timing_names_exactly_the_fields_the_verb_takes():
    """An extra or renamed key is rejected by the daemon, not ignored by it."""
    schema = DAEMON["VERB_SCHEMAS"]["can-fd-up"]

    assert set(FD_TIMING) == set(schema) - {"iface"}


def test_the_drivers_timing_becomes_the_ip_command_an_operator_would_type():
    _verb, _args, commands = validate("can-fd-up", {"iface": "can0", **FD_TIMING})

    assert commands == [
        ["/usr/sbin/ip", "link", "set", "dev", "can0", "down"],
        [
            "/usr/sbin/ip", "link", "set", "dev", "can0", "type", "can",
            "bitrate", "500000", "sample-point", "0.750",
            "dbitrate", "2000000", "dsample-point", "0.750", "fd", "on",
        ],
        ["/usr/sbin/ip", "link", "set", "dev", "can0", "up"],
    ]
