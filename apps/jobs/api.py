from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record

from . import services
from .models import Job


def _visible(request, pk: int) -> Job:
    job = get_object_or_404(Job, pk=pk)
    if job.created_by_id != request.user.pk and not request.user.has_perm("access.manage_any_job"):
        from django.http import Http404
        raise Http404
    return job


class JobStatus(APIView):
    def get(self, request, pk: int):
        return Response(services.deliver(_visible(request, pk)))


class JobCancel(APIView):
    def post(self, request, pk: int):
        job = _visible(request, pk)
        ok = services.cancel(job)
        record("jobs.cancelled", request=request, obj=job, accepted=ok)
        return Response({"cancelled": ok, "note": "A generation already running may finish before the next job starts."})


class JobRequeue(APIView):
    def post(self, request, pk: int):
        if not request.user.has_perm("access.manage_any_job"):
            return Response(status=403)
        job = get_object_or_404(Job, pk=pk)
        ok = services.requeue(job)
        record("jobs.requeued", request=request, obj=job, accepted=ok)
        return Response({"requeued": ok})
