from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.services import scope_for
from apps.audit.services import record
from apps.documents.services import readable_documents

from . import services
from .export import ExportBlocked, to_xlsx
from .models import TCSet, TCTemplate


class StartSerializer(serializers.Serializer):
    collection = serializers.IntegerField(required=False)
    document = serializers.IntegerField(required=False)
    requirement = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    template = serializers.IntegerField(required=False)
    fill_priority = serializers.BooleanField(required=False, default=False)
    lang = serializers.ChoiceField(choices=["en", "ar"], required=False, default="en")


def _visible_set(request, pk: int) -> TCSet:
    tc_set = get_object_or_404(TCSet.objects.select_related("template"), pk=pk)
    scope = scope_for(request.user)
    if tc_set.created_by_id != request.user.pk or not scope.can_read(tc_set.collection_id):
        from django.http import Http404
        raise Http404
    return tc_set


class Sets(APIView):
    def get(self, request):
        rows = TCSet.objects.filter(created_by=request.user).values(
            "id", "title", "status", "summary", "created_at", "job_id")[:100]
        return Response(list(rows))

    def post(self, request):
        ser = StartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        scope = scope_for(request.user)
        document = None
        if data.get("document"):
            document = get_object_or_404(readable_documents(scope), pk=data["document"])
        template = get_object_or_404(TCTemplate, pk=data["template"]) if data.get("template") else None
        try:
            tc_set = services.start_generation(
                user=request.user, scope=scope, collection_id=data.get("collection") or 0, document=document,
                requirement_query=data.get("requirement", ""), instructions=data.get("instructions", ""),
                template=template, fill_priority=data["fill_priority"], lang=data["lang"], request=request)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"id": tc_set.pk, "job_id": tc_set.job_id}, status=202)


class SetDetail(APIView):
    def get(self, request, pk: int):
        tc_set = _visible_set(request, pk)
        columns = tc_set.template.columns
        cases = [{"ordinal": tc.ordinal, "fields": tc.fields, "steps": tc.steps, "scenario_type": tc.scenario_type,
                  "assumption": tc.assumption, "section": tc.section,
                  "sources": [{"title": s.title, "version_no": s.version_no, "locator": s.locator,
                               "section_path": s.section_path} for s in tc.sources.all()]}
                 for tc in tc_set.cases.prefetch_related("sources")]
        return Response({"id": tc_set.pk, "title": tc_set.title, "status": tc_set.status, "summary": tc_set.summary,
                         "columns": columns, "cases": cases, "job_id": tc_set.job_id})


class Export(APIView):
    def get(self, request, pk: int):
        if not request.user.has_perm("access.export_excel"):
            return Response(status=403)
        tc_set = _visible_set(request, pk)
        try:
            data = to_xlsx(tc_set)
        except ExportBlocked as exc:
            return Response({"detail": str(exc), "problems": exc.problems}, status=422)
        record("testcases.exported", request=request, obj=tc_set, cases=tc_set.cases.count())
        response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="etqa-test-cases-{tc_set.pk}.xlsx"'
        return response


class Templates(APIView):
    def get(self, request):
        services.default_template()
        return Response(list(TCTemplate.objects.values("id", "name", "columns", "is_default")))
