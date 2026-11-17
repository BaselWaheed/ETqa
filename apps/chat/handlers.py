from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.access.scope import build_scope
from apps.ai.services import AIFailed, AIUnavailable, budget, primary_model, run
from apps.jobs.registry import PermanentError, RetryableError, Unavailable, register
from apps.retrieval.services import search

from .answering import build_prompts, check_citations, insufficient_text
from .models import Citation, Message


@register("chat.answer", queue="inference", priority=100, max_attempts=2)
def answer(ctx) -> dict:
    p = ctx.payload
    try:
        user = get_user_model().objects.get(pk=p["user_id"])
    except (KeyError, get_user_model().DoesNotExist) as exc:
        raise PermanentError("user not found") from exc
    try:
        out = answer_question(user, p["question"], p.get("lang", "en"), p.get("collection_ids") or None,
                              p.get("history", []), job_id=ctx.job.pk, should_stop=ctx.cancelled,
                              on_stage=lambda stage: ctx.progress({"stage": stage}, force=True),
                              on_text=lambda text: ctx.progress({"stage": "generating", "draft": text}))
    except AIUnavailable as exc:
        raise Unavailable(str(exc)) from exc
    except AIFailed as exc:
        if "cancelled" in str(exc):
            return {"cancelled": True}
        raise RetryableError(str(exc)) from exc
    return _finish(p, out)


def answer_question(user, question: str, lang: str, collection_ids=None, history=None, *, job_id=None,
                    should_stop=None, on_text=None, on_stage=None) -> dict:
    """The full answer path, shared by the chat job and the evaluation command."""
    scope = build_scope(user)  # re-checked at run time: access removed after asking is honoured
    if on_stage:
        on_stage("searching")
    found = search(question, scope, collection_ids=collection_ids)
    notes = list(found.notes)
    retrieved = [{"chunk_id": x.chunk_id, "title": x.document_title, "locator": x.locator} for x in found.passages]
    if not found.passages:
        return _out(insufficient_text(lang), "insufficient", [], "", notes + ["no relevant passages"], retrieved)
    available, tokenizer = budget("chat.answer")
    system, prompt, used = build_prompts(question, lang, found.passages, history or [], available, tokenizer)
    if not used:
        return _out(insufficient_text(lang), "insufficient", [], "", notes + ["passages did not fit the context"], retrieved)
    if on_stage:
        on_stage("generating")
    result = run("chat.answer", prompt, system=system, job_id=job_id, should_stop=should_stop, on_text=on_text)
    text, level, cited = check_citations(result.text, used, lang)
    if any("possible_injection" in pas.flags for pas in used):
        notes.append("a source passage contains text addressed to an AI assistant; review the answer")
    return _out(text, level, cited, result.model_key, notes, retrieved)


def _out(text, level, cited, model_key, notes, retrieved) -> dict:
    return {"answer": text, "evidence": level, "citations": [_citation_dict(m, pas) for m, pas in cited],
            "notes": notes, "model": model_key, "retrieved": retrieved}


def _citation_dict(marker, pas) -> dict:
    return {"marker": marker, "chunk_id": pas.chunk_id, "document_id": pas.document_id, "title": pas.document_title,
            "version_no": pas.version_no, "locator": pas.locator, "section_path": pas.section_path,
            "excerpt": pas.text[:400]}


def _finish(p: dict, out: dict) -> dict:
    citations = out["citations"]
    if p.get("message_id"):
        with transaction.atomic():
            Message.objects.filter(pk=p["message_id"]).update(content=out["answer"], evidence=out["evidence"],
                                                              model_key=out["model"])
            Citation.objects.filter(message_id=p["message_id"]).delete()
            Citation.objects.bulk_create([Citation(
                message_id=p["message_id"], marker=c["marker"], chunk_id=c["chunk_id"], document_id=c["document_id"],
                title=c["title"][:300], version_no=c["version_no"], locator=c["locator"], section_path=c["section_path"],
                excerpt=c["excerpt"]) for c in citations])
    body = {k: v for k, v in out.items() if k != "retrieved"}
    return {**body, "message_id": p.get("message_id")}


__all__ = ["answer", "primary_model"]
