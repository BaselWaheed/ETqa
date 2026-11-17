"""Worker loop: claim, run with heartbeat, finish. One job at a time per worker process."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import traceback

from django.db import close_old_connections
from django.utils import timezone

from apps.sysconfig.services import get as setting

from . import services
from .models import Job, WorkerHeartbeat
from .registry import DeferJob, PermanentError, RetryableError, Unavailable, gate_open, spec

log = logging.getLogger("etqa.jobs")


class JobContext:
    """Passed to handlers: progress writes (throttled), cancellation check."""

    def __init__(self, job: Job, worker_id: str):
        self.job = job
        self.worker_id = worker_id
        self._last_progress = 0.0

    @property
    def payload(self) -> dict:
        return self.job.payload

    def progress(self, data: dict, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_progress >= setting("jobs.progress_interval_seconds"):
            services.write_progress(self.job, self.worker_id, data)
            self._last_progress = now

    def cancelled(self) -> bool:
        return Job.objects.filter(pk=self.job.pk, cancel_requested=True).exists()


class _Heartbeat(threading.Thread):
    def __init__(self, job: Job, worker_id: str):
        super().__init__(daemon=True)
        self.job, self.worker_id = job, worker_id
        self.stop_event = threading.Event()
        self.lost = False

    def run(self):
        try:
            while not self.stop_event.wait(setting("jobs.heartbeat_seconds")):
                if not services.heartbeat(self.job, self.worker_id):
                    self.lost = True
                    return
        finally:
            close_old_connections()


def default_worker_id(queue: str) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{queue}"


def run_one(queue: str, worker_id: str) -> Job | None:
    """Claims and runs at most one job. Returns the job it ran, or None."""
    if not gate_open(queue):
        return None
    job = services.claim(queue, worker_id)
    if job is None:
        return None
    WorkerHeartbeat.objects.update_or_create(worker_id=worker_id, defaults={
        "queue": queue, "last_seen": timezone.now(), "current_job": job})
    handler = spec(job.kind)
    if handler is None:
        services.fail(job, worker_id, f"no handler registered for {job.kind!r}", permanent=True)
        return job
    beat = _Heartbeat(job, worker_id)
    beat.start()
    try:
        result = handler.func(JobContext(job, worker_id)) or {}
        if not services.complete(job, worker_id, result):
            log.warning("job %s finished after its lease was lost or it was cancelled; result discarded", job.pk)
    except DeferJob as exc:
        services.defer(job, worker_id, exc.seconds, str(exc))
    except PermanentError as exc:
        services.fail(job, worker_id, f"{exc.__class__.__name__}: {exc}", permanent=True)
    except (RetryableError, Unavailable) as exc:
        services.fail(job, worker_id, f"{exc.__class__.__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 - unexpected errors are retried, with the traceback kept
        log.exception("job %s (%s) raised", job.pk, job.kind)
        services.fail(job, worker_id, f"{exc.__class__.__name__}: {exc}\n{traceback.format_exc(limit=5)}")
    finally:
        beat.stop_event.set()
        WorkerHeartbeat.objects.filter(worker_id=worker_id).update(last_seen=timezone.now(), current_job=None)
    return job


def run_forever(queue: str, worker_id: str, stop: threading.Event) -> None:
    last_reap = 0.0
    log.info("worker %s started on queue %s", worker_id, queue)
    while not stop.is_set():
        close_old_connections()
        try:
            if time.monotonic() - last_reap > setting("jobs.reaper_seconds"):
                stats = services.reap()
                last_reap = time.monotonic()
                if any(stats.values()):
                    log.info("reaper: %s", stats)
            WorkerHeartbeat.objects.update_or_create(worker_id=worker_id, defaults={"queue": queue, "last_seen": timezone.now()})
            ran = run_one(queue, worker_id)
        except Exception:  # noqa: BLE001 - database blips must not kill the worker
            log.exception("worker loop error; retrying shortly")
            ran = None
            time.sleep(5)
        if ran is None:
            stop.wait(setting("jobs.poll_idle_seconds"))
    log.info("worker %s stopped", worker_id)
