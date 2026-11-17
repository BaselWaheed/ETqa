"""Public interface of the job queue: enqueue, claim, complete, cancel, recover (architecture doc, section 4)."""
from __future__ import annotations

import random
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.sysconfig.services import get as setting

from .models import Job, JobAttempt
from .registry import spec


def enqueue(kind: str, payload: dict | None = None, *, user=None, idempotency_key: str = "", priority: int | None = None,
            queue: str | None = None, max_attempts: int | None = None, ephemeral: bool = False, delay_seconds: float = 0) -> Job:
    """Creates a job, or returns the live job with the same idempotency key."""
    handler = spec(kind)
    queue = queue or (handler.queue if handler else "general")
    priority = priority if priority is not None else (handler.priority if handler else 10)
    max_attempts = max_attempts or (handler.max_attempts if handler and handler.max_attempts else setting("jobs.max_attempts"))
    if idempotency_key:
        existing = Job.objects.filter(kind=kind, idempotency_key=idempotency_key, status__in=Job.LIVE).first()
        if existing:
            return existing
    fields = dict(kind=kind, payload=payload or {}, queue=queue, priority=priority, max_attempts=max_attempts,
                  idempotency_key=idempotency_key, created_by=user if getattr(user, "pk", None) else None, ephemeral=ephemeral)
    if delay_seconds:
        fields["run_after"] = timezone.now() + timedelta(seconds=delay_seconds)
    try:
        with transaction.atomic():
            return Job.objects.create(**fields)
    except IntegrityError:
        return Job.objects.get(kind=kind, idempotency_key=idempotency_key, status__in=Job.LIVE)


# clock_timestamp(), not now(): now() is the transaction start, which can precede a just-inserted run_after.
CLAIM_SQL = """
UPDATE jobs_job SET status = 'running', worker_id = %(worker)s, attempts = attempts + 1,
       lease_until = clock_timestamp() + make_interval(secs => %(lease)s), heartbeat_at = clock_timestamp(),
       started_at = COALESCE(started_at, clock_timestamp())
WHERE id = (
  SELECT id FROM jobs_job
  WHERE queue = %(queue)s AND status IN ('queued', 'retrying') AND run_after <= clock_timestamp()
  ORDER BY (priority + priority_boost) DESC, run_after, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1)
RETURNING id
"""


def claim(queue: str, worker_id: str) -> Job | None:
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(CLAIM_SQL, {"worker": worker_id, "lease": setting("jobs.lease_seconds"), "queue": queue})
            row = cur.fetchone()
    if not row:
        return None
    job = Job.objects.get(pk=row[0])
    JobAttempt.objects.create(job=job, attempt_no=job.attempts, worker_id=worker_id, started_at=timezone.now())
    return job


def heartbeat(job: Job, worker_id: str) -> bool:
    """Extends the lease. False means the lease was lost (job recovered or cancelled)."""
    updated = Job.objects.filter(pk=job.pk, worker_id=worker_id, status=Job.Status.RUNNING).update(
        heartbeat_at=timezone.now(), lease_until=timezone.now() + timedelta(seconds=setting("jobs.lease_seconds")))
    return bool(updated)


def write_progress(job: Job, worker_id: str, progress: dict) -> bool:
    return bool(Job.objects.filter(pk=job.pk, worker_id=worker_id, status=Job.Status.RUNNING).update(progress=progress))


def _finish_attempt(job: Job, outcome: str, error: str = "") -> None:
    JobAttempt.objects.filter(job_id=job.pk, attempt_no=job.attempts).update(
        finished_at=timezone.now(), outcome=outcome, error=error[:4000])


def complete(job: Job, worker_id: str, result: dict) -> bool:
    """Returns False when the lease was lost: the result is discarded."""
    ok = Job.objects.filter(pk=job.pk, worker_id=worker_id, status=Job.Status.RUNNING).update(
        status=Job.Status.COMPLETED, result=result, finished_at=timezone.now(), lease_until=None)
    _finish_attempt(job, "completed" if ok else "lease_lost")
    return bool(ok)


def retry_delay(attempt: int) -> float:
    base, cap = setting("jobs.retry_base_seconds"), setting("jobs.retry_max_seconds")
    return min(cap, base * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


def fail(job: Job, worker_id: str, error: str, *, permanent: bool = False) -> str:
    job.refresh_from_db()
    if permanent:
        status, run_after = Job.Status.DEAD, None
    elif job.attempts >= job.max_attempts:
        status, run_after = Job.Status.FAILED, None
    else:
        status, run_after = Job.Status.RETRYING, timezone.now() + timedelta(seconds=retry_delay(job.attempts))
    fields = dict(status=status, last_error=error[:4000], lease_until=None, worker_id="")
    if run_after:
        fields["run_after"] = run_after
    else:
        fields["finished_at"] = timezone.now()
    Job.objects.filter(pk=job.pk, worker_id=worker_id, status=Job.Status.RUNNING).update(**fields)
    _finish_attempt(job, status, error)
    return status


def defer(job: Job, worker_id: str, seconds: float, reason: str) -> None:
    Job.objects.filter(pk=job.pk, worker_id=worker_id, status=Job.Status.RUNNING).update(
        status=Job.Status.QUEUED, attempts=F("attempts") - 1, lease_until=None, worker_id="",
        run_after=timezone.now() + timedelta(seconds=seconds), last_error=f"deferred: {reason}"[:4000])
    JobAttempt.objects.filter(job_id=job.pk, attempt_no=job.attempts).delete()


def cancel(job: Job) -> bool:
    """Cancel means stop waiting: queued jobs end now; a running job is marked and its late result discarded."""
    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.status in Job.TERMINAL:
            return False
        locked.cancel_requested = True
        locked.status = Job.Status.CANCELLED
        locked.finished_at = timezone.now()
        locked.lease_until = None
        locked.save(update_fields=["cancel_requested", "status", "finished_at", "lease_until"])
    return True


def requeue(job: Job) -> bool:
    updated = Job.objects.filter(pk=job.pk, status__in=[Job.Status.FAILED, Job.Status.DEAD]).update(
        status=Job.Status.QUEUED, attempts=0, run_after=timezone.now(), finished_at=None, last_error="", priority_boost=0)
    return bool(updated)


def reap() -> dict:
    """Recovers expired leases, applies the starvation boost, purges old and ephemeral data."""
    now = timezone.now()
    recovered = failed = 0
    for job in Job.objects.filter(status=Job.Status.RUNNING, lease_until__lt=now):
        exhausted = job.attempts >= job.max_attempts
        n = Job.objects.filter(pk=job.pk, status=Job.Status.RUNNING, lease_until__lt=now).update(
            status=Job.Status.FAILED if exhausted else Job.Status.RETRYING, worker_id="", lease_until=None,
            last_error="lease expired", finished_at=now if exhausted else None, run_after=now)
        JobAttempt.objects.filter(job_id=job.pk, attempt_no=job.attempts, finished_at__isnull=True).update(
            finished_at=now, outcome="lease_expired")
        failed += n if exhausted else 0
        recovered += 0 if exhausted else n
    period = timedelta(minutes=setting("jobs.boost_after_minutes"))
    step, cap = setting("jobs.boost_step"), setting("jobs.boost_cap")
    boosted = 0
    for job in Job.objects.filter(status__in=[Job.Status.QUEUED, Job.Status.RETRYING], run_after__lt=now - period,
                                  priority_boost__lt=cap).only("id", "run_after"):
        target = min(cap, step * int((now - job.run_after) / period))
        boosted += Job.objects.filter(pk=job.pk, priority_boost__lt=target).update(priority_boost=target)
    cleared = Job.objects.filter(ephemeral=True, status__in=Job.TERMINAL,
                                 finished_at__lt=now - timedelta(minutes=setting("jobs.ephemeral_ttl_minutes"))) \
        .exclude(payload={}, result={}, progress={}).update(payload={}, result={}, progress={})
    purged, _ = Job.objects.filter(status__in=[Job.Status.COMPLETED, Job.Status.CANCELLED],
                                   finished_at__lt=now - timedelta(days=setting("jobs.completed_retention_days"))).delete()
    return {"recovered": recovered, "failed": failed, "boosted": boosted, "ephemeral_cleared": cleared, "purged": purged}


def queue_position(job: Job) -> int | None:
    if job.status not in (Job.Status.QUEUED, Job.Status.RETRYING):
        return None
    effective = job.priority + job.priority_boost
    ahead = Job.objects.filter(queue=job.queue, status__in=[Job.Status.QUEUED, Job.Status.RETRYING]).exclude(pk=job.pk)
    ahead = ahead.annotate(eff=F("priority") + F("priority_boost")).filter(eff__gt=effective).count() + \
        ahead.annotate(eff=F("priority") + F("priority_boost")).filter(eff=effective, run_after__lt=job.run_after).count()
    running = Job.objects.filter(queue=job.queue, status=Job.Status.RUNNING).count()
    return ahead + running + 1


def deliver(job: Job) -> dict:
    """Status for the API. An ephemeral job's text is cleared once its owner has received the final result."""
    body = {"id": job.pk, "kind": job.kind, "status": job.status, "position": queue_position(job),
            "progress": job.progress, "result": job.result if job.status == Job.Status.COMPLETED else None,
            "error": job.last_error if job.status in (Job.Status.FAILED, Job.Status.DEAD) else None,
            "retrying": job.status == Job.Status.RETRYING}
    if job.ephemeral and job.status in Job.TERMINAL and (job.payload or job.result or job.progress):
        Job.objects.filter(pk=job.pk).update(payload={}, result={}, progress={})
    return body
