"""Public interface of the documents module."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from apps.access.scope import AccessScope, can_upload
from apps.audit.services import record
from apps.jobs.services import enqueue

from . import storage
from .models import Document, DocumentVersion
from .validation import UploadRejected, detect_type


class NotAllowed(Exception):
    pass


class Duplicate(Exception):
    def __init__(self, version: DocumentVersion):
        super().__init__("This exact file is already in the collection.")
        self.version = version


def readable_documents(scope: AccessScope):
    return Document.objects.filter(collection_id__in=scope.readable, status=Document.Status.ACTIVE)


def upload(*, user, scope: AccessScope, collection_id: int, uploaded, title: str = "", document: Document | None = None,
           request=None) -> DocumentVersion:
    """Validates, stores and registers a file, then queues ingestion. `document` adds a new version."""
    if document is not None:
        collection_id = document.collection_id
    if not can_upload(user, scope, collection_id):
        raise NotAllowed("You cannot upload to this collection.")
    file_type = detect_type(uploaded)
    sha, rel, size = storage.store(uploaded)
    existing = DocumentVersion.objects.filter(sha256=sha, document__collection_id=collection_id,
                                              document__status=Document.Status.ACTIVE).select_related("document").first()
    if existing:
        raise Duplicate(existing)
    with transaction.atomic():
        if document is None:
            document = Document.objects.create(collection_id=collection_id, created_by=user,
                                               title=(title or uploaded.name)[:300])
        next_no = (document.versions.aggregate(m=Max("version_no"))["m"] or 0) + 1
        version = DocumentVersion.objects.create(document=document, version_no=next_no, sha256=sha, file_path=rel,
                                                 original_name=uploaded.name[:255], file_type=file_type,
                                                 size_bytes=size, uploaded_by=user)
        document.current_version = version
        document.save(update_fields=["current_version", "updated_at"])
        # Same transaction as the version row: a worker sees both or neither.
        enqueue("ingest.version", {"version_id": version.pk}, user=user, idempotency_key=f"ingest:{version.pk}",
                priority=50)
    record("documents.uploaded", actor=user, obj=document, request=request, version=next_no, file_type=file_type,
           size_bytes=size)
    return version


def reingest(version: DocumentVersion, *, user, request=None):
    record("documents.reingest", actor=user, obj=version.document, request=request, version=version.version_no)
    return enqueue("ingest.version", {"version_id": version.pk}, user=user, idempotency_key=f"ingest:{version.pk}", priority=40)


def archive(document: Document, *, user, request=None) -> None:
    document.status = Document.Status.ARCHIVED
    document.save(update_fields=["status", "updated_at"])
    record("documents.archived", actor=user, obj=document, request=request)


__all__ = ["upload", "reingest", "archive", "readable_documents", "UploadRejected", "Duplicate", "NotAllowed"]
