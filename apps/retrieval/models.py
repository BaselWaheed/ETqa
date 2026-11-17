from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models.functions import Lower


class Chunk(models.Model):
    """A retrievable passage. collection_id is denormalized so access filters run on this table alone (ADR-07)."""

    version = models.ForeignKey("documents.DocumentVersion", on_delete=models.CASCADE, related_name="chunks")
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="+")
    collection = models.ForeignKey("access.Collection", on_delete=models.CASCADE, related_name="+")
    ordinal = models.PositiveIntegerField()
    section_path = models.CharField(max_length=500, blank=True)
    locator = models.CharField(max_length=120, help_text="Page number, sheet name or section, for citations.")
    text = models.TextField(help_text="Original text, shown and cited.")
    search_text = models.TextField(help_text="Normalized text used for full-text search (ADR-06).")
    identifiers = models.TextField(blank=True)
    tsv = SearchVectorField(null=True)
    lang = models.CharField(max_length=5, default="en")
    token_count = models.PositiveIntegerField(default=0)
    flags = models.JSONField(default=list, blank=True, help_text="e.g. possible_injection")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "ordinal"], name="uniq_chunk_ordinal")]
        indexes = [
            models.Index(fields=["collection"]),
            GinIndex(fields=["tsv"], name="chunk_tsv_gin"),
            GinIndex(OpClass(Lower("identifiers"), name="gin_trgm_ops"), name="chunk_ident_trgm"),
        ]


class EmbeddingSpace(models.Model):
    """One embedding model version; vectors from different spaces are never compared (ADR-10)."""

    model_key = models.CharField(max_length=60)
    runtime_name = models.CharField(max_length=120)
    dims = models.PositiveIntegerField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["model_key", "runtime_name", "dims"], name="uniq_space"),
            models.UniqueConstraint(fields=["is_active"], condition=models.Q(is_active=True), name="one_active_space"),
        ]

    def __str__(self) -> str:
        return f"{self.model_key} ({self.dims}d){' active' if self.is_active else ''}"


class ChunkEmbedding(models.Model):
    chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="embeddings")
    space = models.ForeignKey(EmbeddingSpace, on_delete=models.CASCADE, related_name="+")
    vector = ArrayField(models.FloatField())

    class Meta:
        constraints = [models.UniqueConstraint(fields=["chunk", "space"], name="uniq_chunk_space")]
