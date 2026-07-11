import logging
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


def frame_data_from_fields(frame_fields: List[Dict[str, Any]]) -> bytes:
    """Serialize field values as hex bytes, falling back to UTF-8 text."""
    try:
        frame_data = bytearray()
        for field in frame_fields:
            value = field.get("value", "")
            if not value:
                continue
            value = value.removeprefix("0x")
            try:
                frame_data.extend(bytes.fromhex(value))
            except ValueError:
                frame_data.extend(value.encode("utf-8"))
        return bytes(frame_data)
    except Exception as error:
        logger.error("Error creating frame data: %s", error)
        return b""
