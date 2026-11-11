"""Native document parsers, using the existing isolated-worker campaign.

Build ui/can's network-description cdylib before selecting this target pack.
This optional pack is explicit so Python-only installations need no Rust build.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..harnesses.parser_targets import ParseTarget, register


class RustParserError(ValueError):
    """The native parser rejected an input file."""


@lru_cache(maxsize=1)
def _library() -> Any:
    library = ctypes.CDLL(os.environ["IOTSPLOIT_RUST_PARSER_LIBRARY"])
    library.network_description_probe.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint8,
    ]
    library.network_description_probe.restype = ctypes.c_uint8
    return library


def _parse(payload: bytes, format_id: int) -> dict:
    buffer = ctypes.create_string_buffer(payload)
    status = _library().network_description_probe(buffer, len(payload), format_id)
    if status == 1:
        raise RustParserError("Native document parser rejected the file")
    if status != 0:
        raise RuntimeError(f"Invalid native parser status: {status}")
    return {"parsed": True}


def parse_dbc(payload: bytes) -> dict:
    """Run the same Rust DBC parser and bounded queries used by Flutter."""
    return _parse(payload, 0)


def parse_arxml(payload: bytes) -> dict:
    """Run full AUTOSAR loading, reference resolution, and bounded queries."""
    return _parse(payload, 1)


# Python-only installations can import this module without a native build.
# Selecting the native gate explicitly supplies the library and shared corpus.
if os.environ.get("IOTSPLOIT_RUST_PARSER_LIBRARY"):
    _CAN = Path(__file__).resolve().parents[4] / "ui/can"
    _FIXTURES = _CAN / "fixtures/network-descriptions"
    # Fingerprint source + pinned dependencies rather than a machine-specific
    # binary hash, so retained ledgers replay on another developer's machine.
    _VERSION = hashlib.sha256(b"".join(
        path.read_bytes() for path in (
            _CAN / "Cargo.lock",
            _CAN / "crates/can-core/src/dbc.rs",
            _CAN / "crates/network-description/src/lib.rs",
        )
    )).hexdigest()
    for _name, _adapter, _file in (
        ("rust.parse_dbc", "parse_dbc", "motohawk.dbc"),
        ("rust.parse_arxml", "parse_arxml", "system-4.2.arxml"),
    ):
        register(
            ParseTarget(
                name=_name,
                adapter=f"{__name__}:{_adapter}",
                declared=(f"{__name__}:RustParserError",),
                seeds=((_FIXTURES / _file).read_bytes(), b"", b"<!DOCTYPE a []><a/>"),
                adapter_version=_VERSION,
                budget_seconds=5.0,
            )
        )
