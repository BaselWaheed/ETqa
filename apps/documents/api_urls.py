from django.urls import path

from . import api

urlpatterns = [
    path("documents/", api.DocumentList.as_view(), name="api-documents"),
    path("documents/<int:pk>/", api.DocumentDetail.as_view(), name="api-document"),
    path("documents/<int:pk>/reingest/", api.Reingest.as_view(), name="api-document-reingest"),
    path("documents/<int:pk>/versions/<int:version_id>/file/", api.VersionFile.as_view(), name="api-document-file"),
]
