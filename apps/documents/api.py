from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.services import scope_for
from apps.audit.services import record

from . import services, storage
from .models import Document
from .serializers import DocumentDetailSerializer, DocumentSerializer, VersionSerializer


def _readable(request, pk: int) -> Document:
    return get_object_or_404(services.readable_documents(scope_for(request.user)).select_related("collection"), pk=pk)


class DocumentList(APIView):
    parser_classes = [MultiPartParser]

    def get(self, request):
        qs = services.readable_documents(scope_for(request.user)).select_related("collection", "current_version")
        if request.query_params.get("collection"):
            qs = qs.filter(collection_id=request.query_params["collection"])
        return Response(DocumentSerializer(qs[:500], many=True).data)

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Choose a file to upload."}, status=400)
        try:
            collection_id = int(request.data.get("collection", 0))
        except ValueError:
            return Response({"detail": "Choose a collection."}, status=400)
        document = None
        if request.data.get("document"):
            document = _readable(request, int(request.data["document"]))
        try:
            version = services.upload(user=request.user, scope=scope_for(request.user), collection_id=collection_id,
                                      uploaded=uploaded, title=request.data.get("title", ""), document=document,
                                      request=request)
        except services.NotAllowed as exc:
            return Response({"detail": str(exc)}, status=403)
        except services.UploadRejected as exc:
            return Response({"detail": str(exc)}, status=400)
        except services.Duplicate as exc:
            return Response({"detail": str(exc), "document": exc.version.document_id}, status=409)
        return Response(DocumentDetailSerializer(version.document).data, status=201)


class DocumentDetail(APIView):
    def get(self, request, pk: int):
        return Response(DocumentDetailSerializer(_readable(request, pk)).data)

    def delete(self, request, pk: int):
        document = _readable(request, pk)
        if not request.user.has_perm("access.delete_documents"):
            return Response(status=403)
        services.archive(document, user=request.user, request=request)
        return Response(status=204)


class Reingest(APIView):
    def post(self, request, pk: int):
        document = _readable(request, pk)
        scope = scope_for(request.user)
        if not (scope.can_manage(document.collection_id) or request.user.has_perm("access.delete_documents")):
            return Response(status=403)
        job = services.reingest(document.current_version, user=request.user, request=request)
        return Response({"job_id": job.pk}, status=202)


class VersionFile(APIView):
    """Authorized download of an original; the storage path is never exposed."""

    def get(self, request, pk: int, version_id: int):
        document = _readable(request, pk)
        version = get_object_or_404(document.versions, pk=version_id)
        try:
            handle = open(storage.path_of(version.file_path), "rb")  # noqa: SIM115 - FileResponse closes it
        except OSError:
            raise Http404
        record("documents.downloaded", request=request, obj=document, version=version.version_no)
        return FileResponse(handle, as_attachment=True, filename=version.original_name)
