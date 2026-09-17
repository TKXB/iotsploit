"""Read-only CAN monitor helpers exposed to the operator UI."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_protocols.canbus import TargetCanCatalog
from iotsploit_protocols.canbus.bus_match import observe_identities, score_buses
from iotsploit_protocols.canbus.logfile import (
    CanLogError,
    identities_from_log,
    normalize_log_channel,
    scan_log,
    select_log_channel,
)
from iotsploit_protocols.errors import NotConfigured, ProtocolError


@csrf_exempt
def identify_can_bus(request):
    """POST a target and interface, then score a short read-only sample."""
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST is allowed"}, status=405
        )
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Body is not valid JSON"}, status=400
        )

    target_id = str(body.get("target_id") or "").strip()
    channel = str(body.get("channel") or "").strip()
    # A recorded log needs this scorer more than a live bus does, not less:
    # picking the wrong bus decodes every frame to a plausible wrong value
    # either way, and whoever reads a log back is often not whoever recorded it.
    path = str(body.get("path") or "").strip()
    if not target_id or not (channel or path):
        return JsonResponse(
            {
                "status": "error",
                "message": "target_id and either channel or path are required",
            },
            status=400,
        )
    if channel and path:
        return JsonResponse(
            {
                "status": "error",
                "message": "give either a channel to listen on or a path to read, not both",
            },
            status=400,
        )
    try:
        seconds = float(body.get("seconds", 6.0))
        if not 0 < seconds <= 30:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse(
            {"status": "error", "message": "seconds must be greater than 0 and at most 30"},
            status=400,
        )

    try:
        log_channel = normalize_log_channel(body.get("log_channel"))
    except ValueError as error:
        return JsonResponse({"status": "error", "message": str(error)}, status=400)

    stored = TargetManager.get_instance().get_target(target_id)
    if stored is None:
        return JsonResponse(
            {"status": "error", "message": f"Target '{target_id}' not found"}, status=404
        )

    try:
        if path:
            inspected = scan_log(path, channel=log_channel, max_frames=5_000_000)
            log_channel = select_log_channel(inspected.channels_present, log_channel)
            seen = identities_from_log(path, channel=log_channel)
        else:
            seen = observe_identities(channel, seconds, fd=body.get("fd", True) is not False)
        result = score_buses(TargetCanCatalog.from_target(stored), seen)
    except (NotConfigured, ProtocolError, CanLogError, OSError, ValueError) as error:
        return JsonResponse({"status": "error", "message": str(error)}, status=400)

    source = {"path": path, "log_channel": log_channel} if path else {
        "channel": channel,
        "seconds": seconds,
    }
    return JsonResponse(
        {
            "status": "success",
            **source,
            "identities_heard": len(seen),
            **result.as_dict(),
        }
    )


@csrf_exempt
def inspect_can_log(request):
    """Validate an uploaded log and return the format and buses it contains."""
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST is allowed"}, status=405
        )
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Body is not valid JSON"}, status=400
        )

    path = str(body.get("path") or "").strip()
    if not path:
        return JsonResponse(
            {"status": "error", "message": "path is required"}, status=400
        )

    try:
        stats = scan_log(path, max_frames=5_000_000)
        if not stats.channels_present:
            raise CanLogError("the CAN log contains no readable frames")
    except (CanLogError, OSError, ValueError) as error:
        return JsonResponse({"status": "error", "message": str(error)}, status=400)

    return JsonResponse({"status": "success", **stats.as_dict()})
