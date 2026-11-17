from django.conf import settings
from django.db import models


class Document(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    collection = models.ForeignKey("access.Collection", on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    current_version = models.ForeignKey("DocumentVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["collection", "status"])]

    def __str__(self) -> str:
        return self.title


class DocumentVersion(models.Model):
    class Ingest(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        NEEDS_REVIEW = "needs_review"
        FAILED = "failed"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    file_path = models.CharField(max_length=200, help_text="Relative to ETQA_FILE_ROOT; never shown to users.")
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=8)
    size_bytes = models.BigIntegerField()
    ingest_status = models.CharField(max_length=14, choices=Ingest.choices, default=Ingest.PENDING)
    ingest_error = models.TextField(blank=True)
    language = models.CharField(max_length=5, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    embedded = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_no"]
        constraints = [models.UniqueConstraint(fields=["document", "version_no"], name="uniq_document_version")]

    def __str__(self) -> str:
        return f"{self.document} v{self.version_no}"


class ExtractionPage(models.Model):
    """What extraction produced per page or sheet, kept for inspection against the original."""

    version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE, related_name="pages")
    locator = models.CharField(max_length=120)
    method = models.CharField(max_length=10)  # text | ocr | vision
    raw_text = models.TextField(blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "locator", "method"], name="uniq_extraction_page")]
