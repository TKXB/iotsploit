import json

from django.http import JsonResponse


def parse_json_body(request):
    return json.loads(request.body)


def method_not_allowed(method: str) -> JsonResponse:
    return JsonResponse(
        {"status": "error", "message": f"Only {method} method is allowed"},
        status=405,
    )
