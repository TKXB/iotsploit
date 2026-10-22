"""Compatibility helpers for Scapy's SOME/IP packet representations."""

from __future__ import annotations


def application_payload(packet) -> bytes:
    """Return application bytes from Scapy 2.6 and 2.7 SOME/IP packets."""
    data = getattr(packet, "data", None)
    if data is not None:
        return b"".join(bytes(item) for item in data)
    return bytes(packet.payload) if packet.payload else b""
