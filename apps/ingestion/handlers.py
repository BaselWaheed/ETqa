"""Job handlers: ingest.version (general), embed.version (general), vision.version (inference)."""
from __future__ import annotations

import base64
import logging
import shlex
import subprocess

from django.db import transaction

from apps.ai import client as ai_client
from apps.ai.models import AIModel
from apps.ai.services import AIFailed, AIUnavailable, embed, primary_model, run
from apps.ai.prompts import get as prompt
from apps.ai.vision import VisionWindow, WindowNotReady
from apps.documents import storage
from apps.documents.models import Document, DocumentVersion, ExtractionPage
from apps.jobs.models import Job
from apps.jobs.registry import DeferJob, PermanentError, RetryableError, register
from apps.jobs.services import enqueue
from apps.retrieval import services as retrieval
from apps.retrieval import text as textutil
from apps.sysconfig.services import get as setting

from .chunker import chunk_blocks
from .extractors import ExtractionError, extract

log = logging.getLogger("etqa.ingestion")


def _set(version: DocumentVersion, **fields) -> None:
    DocumentVersion.objects.filter(pk=version.pk).update(**fields)


def _antivirus(path: str) -> None:
    template = setting("security.av_command").strip()
    if not template:
        return
    cmd = shlex.split(template.replace("{path}", f'"{path}"'), posix=False)
    cmd = [part.strip('"') for part in cmd]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RetryableError(f"antivirus scan could not run: {exc}") from exc
    if result.returncode != 0:
        raise PermanentError("the antivirus scan flagged this file")


@register("ingest.version", queue="general", priority=50)
def ingest_version(ctx) -> dict:
    try:
        version = DocumentVersion.objects.select_related("document").get(pk=ctx.payload["version_id"])
    except (KeyError, DocumentVersion.DoesNotExist) as exc:
        raise PermanentError("document version not found") from exc
    if version.document.status != Document.Status.ACTIVE:
        return {"skipped": "document archived"}
    _set(version, ingest_status=DocumentVersion.Ingest.PROCESSING, ingest_error="")
    path = storage.path_of(version.file_path)
    if not path.exists():
        _set(version, ingest_status=DocumentVersion.Ingest.NEEDS_REVIEW, ingest_error="original file is missing")
        raise PermanentError("original file is missing from the file store")
    try:
        _antivirus(str(path))
        ctx.progress({"stage": "extracting"}, force=True)
        extraction = extract(str(path), version.file_type)
    except PermanentError as exc:
        _set(version, ingest_status=DocumentVersion.Ingest.FAILED, ingest_error=str(exc))
        raise
    except ExtractionError as exc:
        _set(version, ingest_status=DocumentVersion.Ingest.FAILED, ingest_error=str(exc))
        raise PermanentError(str(exc)) from exc

    tokenizer = ""
    try:
        tokenizer = primary_model("embed").tokenizer_path
    except AIUnavailable:
        pass
    ctx.progress({"stage": "chunking"}, force=True)
    chunks = chunk_blocks(extraction.blocks, tokenizer)
    review = any(p.needs_review for p in extraction.pages) or not chunks
    all_text = "\n".join(c["text"] for c in chunks)
    with transaction.atomic():
        ExtractionPage.objects.filter(version=version).exclude(method="vision").delete()
        ExtractionPage.objects.bulk_create([
            ExtractionPage(version=version, locator=p.locator[:120], method=p.method, raw_text=p.text,
                           ocr_confidence=p.confidence, needs_review=p.needs_review, note=p.note[:300])
            for p in extraction.pages], ignore_conflicts=True)
        n = retrieval.replace_chunks(version, chunks)
        _set(version, ingest_status=DocumentVersion.Ingest.NEEDS_REVIEW if review else DocumentVersion.Ingest.READY,
             ingest_error="" if chunks else "No text could be extracted; check the original.",
             language=textutil.detect_language(all_text) if all_text else "", page_count=len(extraction.pages),
             embedded=False)
    if n:
        enqueue("embed.version", {"version_id": version.pk}, idempotency_key=f"embed:{version.pk}", priority=20)
    if extraction.images and setting("vision.enabled"):
        enqueue("vision.version", {"version_id": version.pk, "start": 0}, idempotency_key=f"vision:{version.pk}:0",
                priority=5)
    flagged = sum(1 for c in chunks if c["flags"])
    if flagged:
        log.warning("version %s: %s chunk(s) flagged as possible prompt injection", version.pk, flagged)
    return {"chunks": n, "pages": len(extraction.pages), "images": len(extraction.images),
            "inferred_headings": extraction.inferred_headings, "flagged": flagged, "needs_review": review}


@register("embed.version", queue="general", priority=20)
def embed_version(ctx) -> dict:
    version_id = ctx.payload["version_id"]
    try:
        model = primary_model("embed")
    except AIUnavailable as exc:
        raise DeferJob(300, str(exc)) from exc
    space = retrieval.EmbeddingSpace.objects.filter(model_key=model.key, runtime_name=model.runtime_name).first()
    done = 0
    while True:
        if space is None:
            sample = retrieval.Chunk.objects.filter(version_id=version_id).order_by("ordinal").first()
            if sample is None:
                return {"embedded": 0}
            try:
                vec, _ = embed([sample.section_path + "\n" + sample.text])
            except AIUnavailable as exc:
                raise DeferJob(300, "AI service unavailable; semantic indexing stays pending") from exc
            except AIFailed as exc:
                raise RetryableError(str(exc)) from exc
            space = retrieval.ensure_space(model.key, model.runtime_name, len(vec[0]))
        batch = list(retrieval.chunks_missing_embeddings(version_id, space)[: setting("embed.batch_size")])
        if not batch:
            break
        try:
            vectors, _ = embed([c.section_path + "\n" + c.text for c in batch])
        except AIUnavailable as exc:
            raise DeferJob(300, "AI service unavailable; semantic indexing stays pending") from exc
        except AIFailed as exc:
            raise RetryableError(str(exc)) from exc
        retrieval.store_embeddings(space, [(c.id, v) for c, v in zip(batch, vectors)])
        done += len(batch)
        ctx.progress({"stage": "embedding", "done": done})
    DocumentVersion.objects.filter(pk=version_id).update(embedded=True)
    return {"embedded": done, "space": space.pk}


def _images_for(version: DocumentVersion) -> list[tuple[str, bytes]]:
    path = str(storage.path_of(version.file_path))
    if version.file_type in ("png", "jpg"):
        return [("image", open(path, "rb").read())]  # noqa: SIM115
    if version.file_type == "docx":
        return extract(path, "docx").images
    return []


@register("vision.version", queue="inference", priority=5)
def vision_version(ctx) -> dict:
    if Job.objects.filter(queue="inference", status__in=[Job.Status.QUEUED, Job.Status.RETRYING],
                          kind="chat.answer").exists():
        raise DeferJob(setting("vision.defer_seconds"), "chats are waiting")
    version = DocumentVersion.objects.select_related("document").get(pk=ctx.payload["version_id"])
    start = int(ctx.payload.get("start", 0))
    images = _images_for(version)[start:]
    if not images:
        return {"described": 0}
    try:
        model = primary_model("vision.describe")
    except AIUnavailable as exc:
        raise DeferJob(600, str(exc)) from exc
    window = VisionWindow()
    described, index = 0, start
    try:
        window.open(model)
        for locator, data in images:
            if not window.has_room():
                break
            try:
                result = run("vision.describe", prompt("vision.describe"), images=[base64.b64encode(data).decode()],
                             job_id=ctx.job.pk)
                text, review = result.text.strip(), "unclear" in result.text.lower()
            except AIFailed as exc:
                text, review = "", True
                log.warning("vision failed for version %s %s: %s", version.pk, locator, exc)
            ExtractionPage.objects.update_or_create(version=version, locator=locator[:120], method="vision", defaults={
                "raw_text": text, "needs_review": review,
                "note": "machine description; check against the image" if text else "vision failed; inspect manually"})
            if text:
                _append_vision_chunk(version, locator, text)
            window.count += 1
            described += 1
            index += 1
    except (WindowNotReady, ai_client.ModelError, AIUnavailable) as exc:
        raise RetryableError(f"vision window could not run: {exc}") from exc
    finally:
        window.close()
    remaining = len(images) - described
    if remaining:
        enqueue("vision.version", {"version_id": version.pk, "start": index},
                idempotency_key=f"vision:{version.pk}:{index}", priority=5)
    if described:
        enqueue("embed.version", {"version_id": version.pk}, idempotency_key=f"embed:{version.pk}", priority=20)
    return {"described": described, "remaining": remaining}


def _append_vision_chunk(version: DocumentVersion, locator: str, text: str) -> None:
    last = retrieval.Chunk.objects.filter(version=version).order_by("-ordinal").values_list("ordinal", flat=True).first()
    body = f"[Image description, machine-generated: {locator}]\n{text}"
    chunk = retrieval.Chunk.objects.create(
        version=version, document_id=version.document_id, collection_id=version.document.collection_id,
        ordinal=(last + 1) if last is not None else 0, section_path="Images", locator=locator[:120], text=body,
        search_text=textutil.normalize(body), identifiers=" ".join(textutil.identifiers(text)),
        lang=textutil.detect_language(text), flags=["vision"])
    from django.contrib.postgres.search import SearchVector
    retrieval.Chunk.objects.filter(pk=chunk.pk).update(tsv=SearchVector("search_text", config="simple"))
    DocumentVersion.objects.filter(pk=version.pk).update(embedded=False)


__all__ = ["ingest_version", "embed_version", "vision_version", "AIModel"]
