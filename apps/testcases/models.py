from django.conf import settings
from django.db import models

DEFAULT_COLUMNS = [
    {"key": "name", "label": "Name"},
    {"key": "status", "label": "Status", "default": "Draft"},
    {"key": "preconditions", "label": "Preconditions"},
    {"key": "objective", "label": "Objective"},
    {"key": "folder", "label": "Folder", "default": "{section}"},
    {"key": "priority", "label": "Priority", "blank_unless_requested": True},
    {"key": "component", "label": "Component", "blank_unless_requested": True},
    {"key": "owner", "label": "Owner"},
    {"key": "steps", "label": "Steps"},
    {"key": "test_data", "label": "Test Data"},
    {"key": "expected_result", "label": "Expected Result"},
]
GENERATED_KEYS = {"name", "preconditions", "objective", "steps", "test_data", "expected_result"}


class TCTemplate(models.Model):
    """Column order and defaults for generated test cases. Columns are configurable; extra columns stay blank
    unless they have a default. Default values may use {section} and {user}."""

    name = models.CharField(max_length=100, unique=True)
    columns = models.JSONField(default=list)
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["is_default"], condition=models.Q(is_default=True),
                                               name="one_default_template")]

    def __str__(self) -> str:
        return self.name


class TCSet(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        READY = "ready"
        PARTIAL = "partial"
        FAILED = "failed"

    title = models.CharField(max_length=200)
    template = models.ForeignKey(TCTemplate, on_delete=models.PROTECT)
    collection = models.ForeignKey("access.Collection", on_delete=models.PROTECT, related_name="+")
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    requirement_query = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    fill_priority = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    job_id = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TestCase(models.Model):
    tc_set = models.ForeignKey(TCSet, on_delete=models.CASCADE, related_name="cases")
    ordinal = models.PositiveIntegerField()
    section = models.CharField(max_length=500, blank=True)
    fields = models.JSONField(default=dict)
    steps = models.JSONField(default=list)
    scenario_type = models.CharField(max_length=20, blank=True)
    assumption = models.BooleanField(default=False)
    validation = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["ordinal"]


class TestCaseSource(models.Model):
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name="sources")
    chunk = models.ForeignKey("retrieval.Chunk", null=True, on_delete=models.SET_NULL, related_name="+")
    document = models.ForeignKey("documents.Document", null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=300)
    version_no = models.PositiveIntegerField(default=1)
    locator = models.CharField(max_length=120, blank=True)
    section_path = models.CharField(max_length=500, blank=True)
