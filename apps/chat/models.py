from django.conf import settings
from django.db import models


class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200)
    collection_ids = models.JSONField(default=list, blank=True)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"])]


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    class Evidence(models.TextChoices):
        PENDING = "pending"
        CITED = "cited"              # every claim tied to evidence markers
        UNSUPPORTED = "unsupported"  # the model answered without valid citations: shown with a warning
        INSUFFICIENT = "insufficient"
        FAILED = "failed"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True)
    lang = models.CharField(max_length=5, default="en")
    evidence = models.CharField(max_length=12, choices=Evidence.choices, blank=True)
    job_id = models.BigIntegerField(null=True, blank=True)
    model_key = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Citation(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="citations")
    marker = models.CharField(max_length=6)
    chunk = models.ForeignKey("retrieval.Chunk", null=True, on_delete=models.SET_NULL, related_name="+")
    document = models.ForeignKey("documents.Document", null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=300)
    version_no = models.PositiveIntegerField(default=1)
    locator = models.CharField(max_length=120, blank=True)
    section_path = models.CharField(max_length=500, blank=True)
    excerpt = models.TextField(blank=True)


class Feedback(models.Model):
    """Capture only (Phase 7 adds the review queue). Feeds the evaluation set."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    rating = models.SmallIntegerField(choices=[(1, "up"), (-1, "down")])
    comment = models.TextField(blank=True)
    suggested_answer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="uniq_feedback")]
