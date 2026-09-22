"""The envelope that carries targets between installations.

``{"targets": [...]}`` was already the de-facto interchange format: the ARXML
importer wrote it, the DBC tool wrote it, ``export_targets_to_json`` wrote it,
and ``parse_and_set_target_from_json`` read it -- each with its own hand-rolled
literal and no agreement on what a malformed file should do. This module is
that format's owner, so the four of them agree by construction.

A file written here carries a header naming the version that produced it. A
file *without* one is still read: that is what every exporter emitted before
this module existed, and refusing those would strand the files already on
operators' disks for no gain. What is refused is a version this build does not
understand, by number -- a silent partial read of a newer format is how an
import quietly loses half a target.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence

#: Bumped only when a reader of version N can no longer be trusted with the
#: file. Adding a field a reader may ignore is not a bump.
EXPORT_VERSION = 1

#: Header key. A sibling of ``targets``, never a wrapper around it, so that a
#: reader written against the headerless format still finds the targets.
ENVELOPE_KEY = "iotsploit_export"

TARGETS_KEY = "targets"


class TargetTransferError(ValueError):
    """A file that cannot be read as a target export.

    Carries a sentence for an operator, not a traceback: the message reaches
    the CLI and the import dialog verbatim.
    """


def build_envelope(targets: Sequence[Mapping[str, Any]], *, source: str) -> Dict[str, Any]:
    """Wrap ``targets`` in the export envelope.

    ``source`` is provenance -- which tool wrote the file -- and is advisory.
    """
    return {
        ENVELOPE_KEY: {
            "version": EXPORT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
        },
        TARGETS_KEY: list(targets),
    }


def read_envelope(data: Any) -> List[Dict[str, Any]]:
    """Return the targets in ``data``, or raise ``TargetTransferError``.

    The header is optional (see the module docstring) but is honoured when
    present.
    """
    if not isinstance(data, Mapping):
        raise TargetTransferError(
            "not a target export: expected a JSON object at the top level, "
            f"found {type(data).__name__}"
        )

    header = data.get(ENVELOPE_KEY)
    if header is not None:
        if not isinstance(header, Mapping):
            raise TargetTransferError(f"not a target export: {ENVELOPE_KEY!r} is not an object")
        version = header.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise TargetTransferError(
                f"not a target export: {ENVELOPE_KEY}.version is {version!r}, expected an integer"
            )
        if version > EXPORT_VERSION:
            raise TargetTransferError(
                f"this export is version {version}; this build reads version {EXPORT_VERSION}. "
                "Update IoTSploit to import it."
            )

    targets = data.get(TARGETS_KEY)
    if targets is None:
        # The common wrong file: some other JSON the operator meant to import
        # elsewhere. Saying so beats importing nothing and reporting success,
        # which is what a plain ``data.get("targets", [])`` does.
        raise TargetTransferError(f"not a target export: no {TARGETS_KEY!r} list")
    if not isinstance(targets, list):
        raise TargetTransferError(
            f"not a target export: {TARGETS_KEY!r} is {type(targets).__name__}, expected a list"
        )

    for index, target in enumerate(targets):
        if not isinstance(target, Mapping):
            raise TargetTransferError(
                f"target at position {index} is {type(target).__name__}, expected an object"
            )
        if not target.get("target_id"):
            raise TargetTransferError(f"target at position {index} has no target_id")

    return [dict(target) for target in targets]
