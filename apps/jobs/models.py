from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        RETRYING = "retrying"
        COMPLETED = "completed"
        FAILED = "failed"
        DEAD = "dead"
        CANCELLED = "cancelled"

    LIVE = (Status.QUEUED, Status.RUNNING, Status.RETRYING)
    TERMINAL = (Status.COMPLETED, Status.FAILED, Status.DEAD, Status.CANCELLED)

    kind = models.CharField(max_length=64)
    queue = models.CharField(max_length=32, default="general")
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    priority = models.IntegerField(default=10)
    priority_boost = models.IntegerField(default=0)
    run_after = models.DateTimeField(db_default=Now())
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    lease_until = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    worker_id = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=200, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)
    cancel_requested = models.BooleanField(default=False)
    ephemeral = models.BooleanField(default=False, help_text="Payload and result are cleared once delivered.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(F("queue"), (F("priority") + F("priority_boost")).desc(), F("run_after"),
                         name="job_claim_idx", condition=Q(status__in=["queued", "retrying"])),
            models.Index(fields=["status", "lease_until"], name="job_lease_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["kind", "idempotency_key"], name="job_live_idempotency",
                                    condition=Q(status__in=["queued", "running", "retrying"]) & ~Q(idempotency_key="")),
        ]

    def __str__(self) -> str:
        return f"{self.kind}#{self.pk} {self.status}"


class JobAttempt(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="attempt_log")
    attempt_no = models.PositiveIntegerField()
    worker_id = models.CharField(max_length=100)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "attempt_no"], name="uniq_job_attempt")]


class WorkerHeartbeat(models.Model):
    worker_id = models.CharField(max_length=100, unique=True)
    queue = models.CharField(max_length=32)
    last_seen = models.DateTimeField()
    current_job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
