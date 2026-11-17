from django.contrib.auth.models import Group
from django.db import models

# Capability codenames, one per row of the permission matrix (architecture doc, section 6).
CAPABILITIES = [
    ("use_chat", "Chat over readable collections"),
    ("save_chat_history", "Keep saved chat history"),
    ("search_documents", "Search and open documents in readable collections"),
    ("upload_documents", "Upload documents to readable collections"),
    ("delete_documents", "Delete or archive documents"),
    ("generate_test_cases", "Generate test cases"),
    ("export_excel", "Export to Excel"),
    ("give_feedback", "Give feedback on answers"),
    ("review_knowledge", "Approve or reject knowledge"),
    ("manage_users", "Manage users, groups and grants"),
    ("manage_collections", "Create collections; read and manage all collections"),
    ("configure_models", "Configure models and routes"),
    ("view_audit", "View audit log and system health"),
    ("manage_any_job", "Requeue or cancel any job"),
]


class Capability(models.Model):
    """Holder for ETqa capability permissions; no table is created."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = CAPABILITIES


class Collection(models.Model):
    """The access-control boundary for documents and knowledge (ADR-07)."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    business_unit = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CollectionGrant(models.Model):
    class Level(models.TextChoices):
        READ = "read", "Read"
        MANAGE = "manage", "Manage"

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="grants")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="collection_grants")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.READ)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["collection", "group"], name="uniq_grant_collection_group")]
        indexes = [models.Index(fields=["group", "collection"])]

    def __str__(self) -> str:
        return f"{self.group} -> {self.collection} ({self.level})"
