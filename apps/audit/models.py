from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only record of security-relevant actions.

    The application database role has no UPDATE/DELETE on this table (scripts/sql/roles.sql).
    `detail` must never contain passwords, tokens, prompt bodies or document text.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_label = models.CharField(max_length=150, blank=True, help_text="Username at the time, kept if the user is removed.")
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.action} by {self.actor_label or '-'}"
