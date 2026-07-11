from django.http import JsonResponse


def method_not_allowed(method: str) -> JsonResponse:
    return JsonResponse(
        {"status": "error", "message": f"Only {method} method is allowed"},
        status=405,
    )
