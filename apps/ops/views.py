from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.permissions import capability

from .checks import check_ai, check_database, check_extensions, check_migrations, check_ocr, check_queue


@require_GET
def public_health(request):
    """Unauthenticated liveness probe: no versions, paths or error text."""
    db = check_database()
    ok = db["status"] == "ok"
    return JsonResponse({"status": "ok" if ok else "degraded", "database": db["status"]}, status=200 if ok else 503)


class AdminHealth(APIView):
    permission_classes = [capability("view_audit")]

    def get(self, request):
        db = check_database()
        body = {"version": settings.ETQA_VERSION, "database": db}
        if db["status"] == "ok":
            body["migrations"] = check_migrations()
            body["extensions"] = check_extensions()
            body["queue"] = check_queue()
            body["ai"] = check_ai()
            body["ocr"] = check_ocr()
        return Response(body)
