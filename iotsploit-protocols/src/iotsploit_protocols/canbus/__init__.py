"""Target-defined CAN: resolve a frame, encode it, decode it, put it on a wire.

Four separations that the implementation may rename but must not merge:

* the **catalogue** is pure target-to-definition logic;
* the **codec** is pure definition-and-values-to-bytes logic, and its inverse;
* **SocketCAN** is explicit I/O behind a small client that owns no state
  between calls;
* **policy** -- what may be sent, and after what confirmation -- belongs to the
  plugin above this package, not here.

Nothing in this package reads the database, the current target, or the
environment, and nothing runs ``sudo`` or changes host networking. A link is
brought up outside IoTSploit; a client here opens a socket on one that is
already up, or fails saying so.

Importing this package stays cheap. ``python-can`` opens platform sockets and
reads host configuration on import, so it is imported inside
:mod:`~iotsploit_protocols.canbus.socketcan` at call time -- which is what lets
a preview run on a host with no CAN interface at all.
"""

from __future__ import annotations

__all__ = [
    "BusDefinition",
    "CanCodec",
    "CanDefinitionError",
    "CanValueError",
    "DecodedFrame",
    "EncodedFrame",
    "FrameDefinition",
    "SignalDefinition",
    "TargetCanCatalog",
    "build_message",
    "canonical_frame_id",
    "decode_frame",
    "encode_frame",
]

from iotsploit_protocols.canbus.catalog import TargetCanCatalog
from iotsploit_protocols.canbus.codec import (
    CanCodec,
    build_message,
    decode_frame,
    encode_frame,
)
from iotsploit_protocols.canbus.definitions import (
    BusDefinition,
    DecodedFrame,
    EncodedFrame,
    FrameDefinition,
    SignalDefinition,
    canonical_frame_id,
)
from iotsploit_protocols.canbus.errors import CanDefinitionError, CanValueError
