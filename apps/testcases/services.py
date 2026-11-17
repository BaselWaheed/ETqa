from __future__ import annotations

from django.db import transaction

from apps.access.scope import AccessScope
from apps.audit.services import record
from apps.jobs.services import enqueue

from .models import DEFAULT_COLUMNS, TCSet, TCTemplate


class NotAllowed(Exception):
    pass


def default_template() -> TCTemplate:
    tpl = TCTemplate.objects.filter(is_default=True).first()
    if tpl is None:
        tpl, _ = TCTemplate.objects.get_or_create(name="ETqa default", defaults={"columns": DEFAULT_COLUMNS, "is_default": True})
    return tpl


def start_generation(*, user, scope: AccessScope, collection_id: int, document=None, requirement_query: str = "",
                     instructions: str = "", template: TCTemplate | None = None, fill_priority: bool = False,
                     lang: str = "en", request=None) -> TCSet:
    if not user.has_perm("access.generate_test_cases"):
        raise NotAllowed("You cannot generate test cases.")
    if document is not None:
        collection_id = document.collection_id
    if not scope.can_read(collection_id):
        raise NotAllowed("You cannot read this collection.")
    if document is None and not requirement_query.strip():
        raise ValueError("Choose a document or describe the requirement.")
    with transaction.atomic():
        tc_set = TCSet.objects.create(
            title=(document.title if document else requirement_query.strip())[:200], template=template or default_template(),
            collection_id=collection_id, document=document, requirement_query=requirement_query.strip(),
            instructions=instructions.strip()[:2000], fill_priority=fill_priority, created_by=user)
        job = enqueue("tc.generate", {"set_id": tc_set.pk, "lang": lang}, user=user, idempotency_key=f"tc:{tc_set.pk}")
        TCSet.objects.filter(pk=tc_set.pk).update(job_id=job.pk)
        tc_set.job_id = job.pk
    record("testcases.generation_started", actor=user, obj=tc_set, request=request)
    return tc_set
