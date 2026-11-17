from __future__ import annotations

import re

from django.db import transaction

from apps.ai.health import ollama_available
from apps.audit.services import record
from apps.jobs.services import enqueue

from .models import Conversation, Message

GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|salam|مرحبا|اهلا|أهلا|السلام عليكم|صباح الخير|مساء الخير)[\s!.,؟?]*$",
                      re.IGNORECASE)
GREETING_REPLY = {"en": "Hello. Ask me about your QA documentation, or describe a feature to design test cases for.",
                  "ar": "مرحبًا. اسألني عن وثائق ضمان الجودة، أو صف ميزة لأصمم لها حالات اختبار."}


class ChatNotAllowed(Exception):
    pass


def answer_language(question: str) -> str:
    """Reply in Arabic when the question is written in Arabic, even with English identifiers mixed in."""
    arabic = len(re.findall(r"[\u0621-\u064A]", question))
    latin = len(re.findall(r"[A-Za-z]", question))
    return "ar" if arabic and arabic / (arabic + latin) >= 0.3 else "en"


def ask(*, user, question: str, conversation_id: int | None = None, collection_ids: list[int] | None = None,
        history: list[dict] | None = None, request=None) -> dict:
    if not user.has_perm("access.use_chat"):
        raise ChatNotAllowed("You do not have access to chat.")
    question = question.strip()[:4000]
    lang = answer_language(question)
    saved = user.has_perm("access.save_chat_history")
    if GREETING.match(question):  # deterministic shortcut: no model call
        return {"immediate": {"answer": GREETING_REPLY["ar" if lang == "ar" else "en"], "evidence": "none", "citations": []},
                "saved": saved}
    payload = {"question": question, "lang": lang, "collection_ids": collection_ids or [], "user_id": user.pk}
    conversation = message = None
    with transaction.atomic():
        if saved:
            if conversation_id:
                conversation = Conversation.objects.get(pk=conversation_id, user=user)
            else:
                conversation = Conversation.objects.create(user=user, title=question[:120], collection_ids=collection_ids or [])
            prior = list(conversation.messages.exclude(evidence="pending").order_by("-created_at")[:8])
            payload["history"] = [{"role": m.role, "content": m.content} for m in reversed(prior)]
            Message.objects.create(conversation=conversation, role="user", content=question, lang=lang)
            message = Message.objects.create(conversation=conversation, role="assistant", lang=lang, evidence="pending")
            payload["message_id"] = message.pk
            conversation.save(update_fields=["updated_at"])
        else:
            payload["history"] = [{"role": h.get("role"), "content": str(h.get("content", ""))[:1500]}
                                  for h in (history or [])][-8:]
        job = enqueue("chat.answer", payload, user=user, ephemeral=not saved)
        if message:
            Message.objects.filter(pk=message.pk).update(job_id=job.pk)
    record("chat.asked", actor=user, request=request, object_type="job", object_id=job.pk, saved=saved)
    return {"job_id": job.pk, "conversation_id": conversation.pk if conversation else None,
            "message_id": message.pk if message else None, "saved": saved, "ai_available": ollama_available()}
