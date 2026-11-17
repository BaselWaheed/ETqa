"""Phase 2: the PostgreSQL job queue (architecture doc, section 4)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.jobs import services
from apps.jobs.models import Job, JobAttempt
from apps.jobs.registry import DeferJob, PermanentError, RetryableError, register, register_queue_gate
from apps.jobs.worker import run_one
from tests.conftest import run_jobs

pytestmark = pytest.mark.django_db
CALLS = []


@register("test.ok", queue="testq")
def _ok(ctx):
    CALLS.append(ctx.job.pk)
    ctx.progress({"step": 1}, force=True)
    return {"value": ctx.payload.get("n", 0) * 2}


@register("test.retry", queue="testq")
def _retry(ctx):
    raise RetryableError("model timeout")


@register("test.permanent", queue="testq")
def _permanent(ctx):
    raise PermanentError("bad payload")


@register("test.defer", queue="testq")
def _defer(ctx):
    raise DeferJob(120, "chats waiting")


@register("test.crash", queue="testq")
def _crash(ctx):
    raise ZeroDivisionError("bug")


def test_enqueue_claim_complete():
    job = services.enqueue("test.ok", {"n": 21})
    assert job.queue == "testq" and job.status == "queued"
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "completed" and job.result == {"value": 42} and job.attempts == 1
    assert job.progress == {"step": 1}
    assert JobAttempt.objects.get(job=job).outcome == "completed"


def test_retryable_error_backs_off_then_fails(setting_override):
    setting_override("jobs.max_attempts", 2)
    job = services.enqueue("test.retry")
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "retrying" and job.run_after > timezone.now() and "model timeout" in job.last_error
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "failed" and job.attempts == 2
    assert list(job.attempt_log.values_list("outcome", flat=True).order_by("attempt_no")) == ["retrying", "failed"]


def test_permanent_error_goes_to_dead_without_retry():
    job = services.enqueue("test.permanent")
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "dead" and job.attempts == 1


def test_unexpected_exception_is_retried_with_traceback():
    job = services.enqueue("test.crash")
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "retrying" and "ZeroDivisionError" in job.last_error


def test_defer_does_not_use_an_attempt():
    job = services.enqueue("test.defer")
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "queued" and job.attempts == 0 and job.run_after > timezone.now() + timedelta(seconds=100)


def test_unknown_kind_is_dead():
    job = services.enqueue("test.nobody", queue="testq")
    run_one("testq", "w1")
    job.refresh_from_db()
    assert job.status == "dead" and "no handler" in job.last_error


def test_idempotency_key_returns_the_live_job():
    a = services.enqueue("test.ok", idempotency_key="ingest:1")
    b = services.enqueue("test.ok", idempotency_key="ingest:1")
    assert a.pk == b.pk and Job.objects.count() == 1
    run_one("testq", "w1")
    c = services.enqueue("test.ok", idempotency_key="ingest:1")  # finished jobs do not block a new one
    assert c.pk != a.pk


def test_priority_and_boost_order():
    old = services.enqueue("test.ok", {"n": 1}, priority=10)
    new = services.enqueue("test.ok", {"n": 2}, priority=25)
    Job.objects.filter(pk=old.pk).update(run_after=timezone.now() - timedelta(minutes=31))
    stats = services.reap()
    old.refresh_from_db()
    assert stats["boosted"] == 1 and old.priority_boost == 20 and old.priority == 10  # stored priority untouched
    assert services.claim("testq", "w1").pk == old.pk  # 10 + 20 beats 25
    assert services.claim("testq", "w1").pk == new.pk


def test_worker_crash_recovery_completes_every_job_once():
    """Phase 2 exit gate: a worker dies mid-job; after restart every job ends completed, none lost or duplicated."""
    CALLS.clear()
    jobs = [services.enqueue("test.ok", {"n": i}) for i in range(3)]
    crashed = services.claim("testq", "dead-worker")  # claimed, then the process 'dies'
    Job.objects.filter(pk=crashed.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    assert services.reap()["recovered"] == 1
    run_jobs("testq")
    statuses = set(Job.objects.filter(pk__in=[j.pk for j in jobs]).values_list("status", flat=True))
    assert statuses == {"completed"}
    assert sorted(CALLS) == sorted(j.pk for j in jobs)  # each handler ran exactly once
    assert not services.complete(crashed, "dead-worker", {"late": True})  # the dead worker's late result is discarded


def test_lost_lease_discards_result():
    job = services.enqueue("test.ok")
    claimed = services.claim("testq", "w1")
    Job.objects.filter(pk=job.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    services.reap()
    assert services.complete(claimed, "w1", {"x": 1}) is False
    assert not services.heartbeat(claimed, "w1")


def test_cancel_queued_and_running():
    queued = services.enqueue("test.ok")
    assert services.cancel(queued)
    queued.refresh_from_db()
    assert queued.status == "cancelled"
    running = services.enqueue("test.ok")
    claimed = services.claim("testq", "w1")
    assert services.cancel(running)
    assert services.complete(claimed, "w1", {"x": 1}) is False  # stop waiting: late result dropped
    assert not services.cancel(running)  # already terminal


def test_ephemeral_job_text_cleared_after_delivery():
    job = services.enqueue("test.ok", {"n": 3, "question": "secret?"}, ephemeral=True)
    run_one("testq", "w1")
    job.refresh_from_db()
    assert services.deliver(job)["result"] == {"value": 6}
    job.refresh_from_db()
    assert job.payload == {} and job.result == {} and job.progress == {}


def test_closed_gate_stops_claiming():
    register_queue_gate("gatedq", lambda: False)
    job = services.enqueue("test.ok", queue="gatedq")
    assert run_one("gatedq", "w1") is None
    job.refresh_from_db()
    assert job.status == "queued"


def test_requeue_failed_job():
    job = services.enqueue("test.permanent")
    run_one("testq", "w1")
    assert services.requeue(job)
    job.refresh_from_db()
    assert job.status == "queued" and job.attempts == 0


def test_job_api_visibility(api, users):
    job = services.enqueue("test.ok", user=users["QA Engineer"])
    assert api(users["QA Engineer"]).get(f"/api/v1/jobs/{job.pk}/").json()["status"] == "queued"
    assert api(users["Viewer"]).get(f"/api/v1/jobs/{job.pk}/").status_code == 404
    assert api(users["Admin"]).get(f"/api/v1/jobs/{job.pk}/").status_code == 200
    assert api(users["QA Engineer"]).post(f"/api/v1/jobs/{job.pk}/requeue/").status_code == 403
    resp = api(users["QA Engineer"]).post(f"/api/v1/jobs/{job.pk}/cancel/")
    assert resp.json()["cancelled"] is True


def test_queue_position(users):
    first = services.enqueue("test.ok", priority=10)
    second = services.enqueue("test.ok", priority=10)
    urgent = services.enqueue("test.ok", priority=100)
    assert services.queue_position(urgent) == 1
    assert services.queue_position(first) == 2 and services.queue_position(second) == 3
