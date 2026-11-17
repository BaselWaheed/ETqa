from django.contrib import admin

from .models import Document, DocumentVersion, ExtractionPage


class VersionInline(admin.TabularInline):
    model = DocumentVersion
    fk_name = "document"
    extra = 0
    can_delete = False
    fields = ("version_no", "original_name", "file_type", "size_bytes", "ingest_status", "ingest_error", "embedded")
    readonly_fields = fields


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "collection", "status", "updated_at")
    list_filter = ("status", "collection")
    search_fields = ("title",)
    inlines = [VersionInline]
    readonly_fields = ("current_version", "created_by")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExtractionPage)
class ExtractionPageAdmin(admin.ModelAdmin):
    list_display = ("version", "locator", "method", "ocr_confidence", "needs_review")
    list_filter = ("needs_review", "method")
    readonly_fields = ("version", "locator", "method", "raw_text", "ocr_confidence", "note")
