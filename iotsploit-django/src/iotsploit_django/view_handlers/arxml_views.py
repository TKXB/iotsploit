"""Upload an AUTOSAR ARXML and preview the target it would create.

The preview is read-only by construction: it parses an uploaded file into the
target wire format, validates it through the same hydration the write path
uses, and returns it. Nothing here touches the database. Creating the target is
a second, explicit call the operator makes to ``create_target`` with the
candidate this endpoint returned.

Format knowledge stays in ``iotsploit_protocols.autosar``; this module is only
the HTTP/upload adapter for it. The raw OEM file lives in a temporary file for
the duration of one parse and is deleted on every exit path -- it is never
stored on the target and never logged.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import PurePath

from django.core.files.uploadhandler import StopUpload, TemporaryFileUploadHandler
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_django.tools.xlogger import xlog
from iotsploit_protocols.autosar import ArxmlImportError, import_arxml
from iotsploit_protocols.autosar.arxml import MAX_ARXML_BYTES

logger = xlog.get_logger("arxml_views")

#: The endpoint's own bound on an upload, kept equal to the parser's limit so a
#: file that would be refused after the transfer is refused during it instead.
MAX_UPLOAD_BYTES = MAX_ARXML_BYTES


class BoundedUploadHandler(TemporaryFileUploadHandler):
    """Stop reading a multipart upload once it exceeds ``MAX_UPLOAD_BYTES``.

    Django's default handlers spool an upload of any size to disk and only then
    hand it to the view, so a size check in the view bounds nothing: the bytes
    have already landed. Raising ``StopUpload`` from ``receive_data_chunk``
    aborts the parse at the chunk that crosses the limit, and
    ``connection_reset=False`` lets Django discard the rest of the request so
    the client still receives a 413 instead of a dropped connection.
    """

    def __init__(self, request=None, limit: int | None = None):
        super().__init__(request)
        # Read the module constant at call time, not at definition time, so a
        # test can lower the limit without transferring 256 MiB to prove it.
        self.limit = MAX_UPLOAD_BYTES if limit is None else limit
        self.received = 0
        #: Read back by the view, which cannot otherwise tell an aborted upload
        #: from one the client never sent.
        self.exceeded = False

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > self.limit:
            self.exceeded = True
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)


def _upload_exceeded(request) -> bool:
    return any(getattr(handler, "exceeded", False) for handler in request.upload_handlers)


@csrf_exempt
def preview_arxml_import(request):
    """
    POST multipart/form-data
    Parse an uploaded ARXML into a complete vehicle target and return it for
    review. Writes nothing.

    Fields:
        file       -- the ARXML upload (required)
        target_id  -- unique id for the proposed new target (required)
        name       -- display name for the proposed new target (required)
        source     -- provenance label; the upload's basename by default

    Returns ``candidate``, ``counts``, ``warnings`` and ``complete_vehicle``.
    The candidate is what the caller then posts to ``create_target``; this
    endpoint deliberately does not create it, so the operator sees the counts
    and warnings before any target exists.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    # Must happen before request.POST/FILES: touching either parses the body
    # with whatever handlers are installed at that moment. If something
    # upstream already read the body, Django refuses the assignment -- the
    # size guard around the temporary copy below is then the only bound left,
    # so it stays even though the handler normally makes it unreachable.
    try:
        request.upload_handlers = [BoundedUploadHandler(request)]
    except AttributeError:
        logger.debug("preview_arxml_import: upload already parsed; bounding the copy only")

    try:
        upload = request.FILES.get("file")
    except Exception as exc:  # a malformed multipart body, not a bad ARXML
        logger.debug(f"preview_arxml_import could not read the upload: {exc}")
        return JsonResponse({"error": "Invalid multipart upload"}, status=400)

    if _upload_exceeded(request):
        return JsonResponse(
            {"error": f"ARXML upload exceeds the {MAX_UPLOAD_BYTES} byte limit"},
            status=413,
        )

    if upload is None:
        return JsonResponse({"error": "file is required"}, status=400)

    target_id = (request.POST.get("target_id") or "").strip()
    name = (request.POST.get("name") or "").strip()
    if not target_id:
        return JsonResponse({"error": "target_id is required"}, status=400)
    if not name:
        return JsonResponse({"error": "name is required"}, status=400)

    # Never trust the client's path. PurePath handles a Windows client posting
    # "C:\\oem\\vehicle.arxml", which posixpath.basename would keep whole.
    filename = PurePath(str(upload.name).replace("\\", "/")).name or "upload.arxml"
    source = (request.POST.get("source") or "").strip() or filename

    handle, temp_path = tempfile.mkstemp(suffix=".arxml")
    try:
        written = 0
        with os.fdopen(handle, "wb") as sink:
            for chunk in upload.chunks():
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    return JsonResponse(
                        {"error": f"ARXML upload exceeds the {MAX_UPLOAD_BYTES} byte limit"},
                        status=413,
                    )
                sink.write(chunk)

        try:
            result = import_arxml(temp_path, target_id=target_id, name=name, source=source)
        except ArxmlImportError as exc:
            # The parser names the temporary file in some messages; the client
            # gets the reason, never a server-local path.
            reason = str(exc).replace(temp_path, filename)
            logger.debug(f"preview_arxml_import rejected {filename}: {exc}")
            return JsonResponse({"error": f"Could not import {filename}: {reason}"}, status=400)
        except Exception as exc:
            logger.error(f"preview_arxml_import failed on {filename}: {type(exc).__name__}")
            return JsonResponse({"error": "Failed to parse the ARXML file"}, status=500)

        candidate = result.target

        # Validate through the same hydration create_target uses, so a preview
        # the operator is asked to confirm cannot be one the write path will
        # refuse. This builds a domain object and discards it; it writes
        # nothing.
        try:
            TargetManager.get_instance().create_target_instance(candidate)
        except Exception as exc:
            logger.debug(f"preview_arxml_import produced an invalid target from {filename}: {exc}")
            return JsonResponse({"error": f"Invalid target: {exc}"}, status=400)

        metadata = candidate.get("properties", {}).get("arxml_import", {})
        return JsonResponse(
            {
                "status": "success",
                "candidate": candidate,
                "counts": dict(result.counts),
                "warnings": list(result.warnings),
                "complete_vehicle": bool(metadata.get("complete_vehicle", True)),
            }
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError as exc:
            logger.error(f"preview_arxml_import could not remove its temporary file: {exc}")
