"""Read-only CAN monitor helpers exposed to the operator UI."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_protocols.canbus import TargetCanCatalog
from iotsploit_protocols.canbus.bus_match import observe_identities, score_buses
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
    if not target_id or not channel:
        return JsonResponse(
            {"status": "error", "message": "target_id and channel are required"},
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

    stored = TargetManager.get_instance().get_target(target_id)
    if stored is None:
        return JsonResponse(
            {"status": "error", "message": f"Target '{target_id}' not found"}, status=404
        )

    try:
        seen = observe_identities(channel, seconds, fd=body.get("fd", True) is not False)
        result = score_buses(TargetCanCatalog.from_target(stored), seen)
    except (NotConfigured, ProtocolError, OSError, ValueError) as error:
        return JsonResponse({"status": "error", "message": str(error)}, status=400)

    return JsonResponse(
        {
            "status": "success",
            "channel": channel,
            "seconds": seconds,
            "identities_heard": len(seen),
            **result.as_dict(),
        }
    )
