from rest_framework import serializers

from .models import Document, DocumentVersion


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = ["id", "version_no", "original_name", "file_type", "size_bytes", "ingest_status", "ingest_error",
                  "language", "page_count", "embedded", "created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    current_version = VersionSerializer(read_only=True)
    collection_name = serializers.CharField(source="collection.name", read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "collection", "collection_name", "status", "current_version", "updated_at"]


class DocumentDetailSerializer(DocumentSerializer):
    versions = VersionSerializer(many=True, read_only=True)

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["versions"]
