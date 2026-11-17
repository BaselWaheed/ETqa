"""Health checks. Later phases add Ollama and worker checks here."""
import time

from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def check_database() -> dict:
    started = time.perf_counter()
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        return {"status": "down", "error": exc.__class__.__name__}


def check_migrations() -> dict:
    try:
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return {"status": "ok" if not pending else "pending", "pending": len(pending)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unknown", "error": exc.__class__.__name__}


def check_extensions() -> dict:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN ('pg_trgm', 'vector')")
            installed = dict(cur.fetchall())
            cur.execute("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
            vector_available = cur.fetchone()[0] > 0
        return {"pg_trgm": installed.get("pg_trgm"), "vector_installed": installed.get("vector"),
                "vector_available": vector_available}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unknown", "error": exc.__class__.__name__}


def check_ai() -> dict:
    from apps.ai.health import ollama_available, pulled_models
    from apps.ai.models import AIModel

    ok = ollama_available(force=True)
    pulled = set(pulled_models())
    models = [{"key": m.key, "runtime_name": m.runtime_name, "enabled": m.enabled,
               "pulled": m.runtime_name in pulled or f"{m.runtime_name}:latest" in pulled}
              for m in AIModel.objects.all()]
    return {"ollama": "ok" if ok else "down", "models": models}


def check_ocr() -> dict:
    """Tesseract is optional: a missing install degrades OCR pages to needs_review, nothing else."""
    from apps.ingestion.ocr import status

    return status()


def check_queue() -> dict:
    from datetime import timedelta

    from django.db.models import Count, Min
    from django.utils import timezone

    from apps.jobs.models import Job, WorkerHeartbeat

    counts = dict(Job.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
    oldest = Job.objects.filter(status__in=["queued", "retrying"]).aggregate(m=Min("created_at"))["m"]
    recent = timezone.now() - timedelta(minutes=2)
    workers = list(WorkerHeartbeat.objects.filter(last_seen__gte=recent).values("worker_id", "queue", "last_seen",
                                                                                 "current_job_id"))
    return {"counts": counts, "oldest_waiting": oldest, "live_workers": workers,
            "queues_without_worker": sorted({"general", "inference"} - {w["queue"] for w in workers})}
