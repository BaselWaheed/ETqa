from __future__ import annotations

import json
from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.access.scope import build_scope
from apps.ai import prompts
from apps.ai.services import AIFailed, AIUnavailable, budget, run
from apps.ai.tokens import count
from apps.jobs.registry import PermanentError, RetryableError, Unavailable, register
from apps.retrieval.models import Chunk
from apps.retrieval.services import Passage, search
from apps.sysconfig.services import get as setting

from .models import GENERATED_KEYS, TCSet, TestCase, TestCaseSource
from .validation import case_problems, is_duplicate


def _passages_for(tc_set: TCSet, scope) -> list[Passage]:
    if tc_set.document_id:
        if tc_set.collection_id not in scope.readable:
            return []
        qs = Chunk.objects.filter(document_id=tc_set.document_id, collection_id__in=scope.readable,
                                  version_id=tc_set.document.current_version_id).select_related("document", "version")
        return [Passage(c.id, c.document_id, c.document.title, c.version_id, c.version.version_no, c.collection_id,
                        c.locator, c.section_path, c.text, 0.0, ["document"], c.flags) for c in qs.order_by("ordinal")]
    found = search(tc_set.requirement_query, scope, collection_ids=[tc_set.collection_id], k=24)
    return found.passages


def _common_section(a: str, b: str) -> str:
    """Shared parent of two section paths ('Refunds > Limits' + 'Refunds > Codes' -> 'Refunds')."""
    common = []
    for x, y in zip(a.split(" > "), b.split(" > ")):
        if x != y:
            break
        common.append(x)
    return " > ".join(common) or a


def _groups(passages: list[Passage], limit_tokens: int, tokenizer: str) -> list[tuple[str, list[Passage]]]:
    """Groups passages by section; merges small neighbouring sections up to the prompt budget."""
    by_section: "OrderedDict[str, list[Passage]]" = OrderedDict()
    for p in passages:
        by_section.setdefault(p.section_path or p.document_title, []).append(p)
    groups: list[tuple[str, list[Passage]]] = []
    for section, items in by_section.items():
        size = sum(count(p.text, tokenizer) for p in items)
        if groups and sum(count(p.text, tokenizer) for p in groups[-1][1]) + size <= limit_tokens // 2:
            groups[-1] = (_common_section(groups[-1][0], section), groups[-1][1] + items)
        else:
            groups.append((section, items))
    return groups[: setting("tc.max_sections_per_set")]


def _evidence(items: list[Passage], limit: int, tokenizer: str) -> tuple[str, list[Passage]]:
    parts, used, total = [], [], 0
    for p in items:
        entry = f"[S{len(used) + 1}] ({p.document_title} v{p.version_no}; {p.locator}; {p.section_path})\n{p.text}"
        cost = count(entry, tokenizer)
        if total + cost > limit:
            break
        parts.append(entry)
        used.append(p)
        total += cost
    return "\n\n".join(parts), used


@register("tc.generate", queue="inference", priority=50, max_attempts=2)
def generate(ctx) -> dict:
    try:
        tc_set = TCSet.objects.select_related("template", "document", "created_by").get(pk=ctx.payload["set_id"])
    except (KeyError, TCSet.DoesNotExist) as exc:
        raise PermanentError("test case set not found") from exc
    user = tc_set.created_by
    scope = build_scope(user)
    TCSet.objects.filter(pk=tc_set.pk).update(status=TCSet.Status.RUNNING)
    passages = _passages_for(tc_set, scope)
    if not passages:
        TCSet.objects.filter(pk=tc_set.pk).update(status=TCSet.Status.FAILED,
                                                  summary={"error": "No readable requirement text was found."})
        return {"cases": 0, "error": "no passages"}
    try:
        available, tokenizer = budget("tc.generate")
    except AIUnavailable as exc:
        raise Unavailable(str(exc)) from exc
    lang = ctx.payload.get("lang", "en")
    system = prompts.get("tc.generate.system").format(language="Arabic" if lang == "ar" else "English")
    template = prompts.get("tc.generate.user")
    groups = _groups(passages, available, tokenizer)
    kept: list[dict] = []
    stats = {"sections": len(groups), "generated": 0, "duplicates": 0, "invalid": 0, "assumptions": 0, "section_errors": []}
    for i, (section, items) in enumerate(groups, 1):
        ctx.progress({"stage": f"section {i} of {len(groups)}", "cases": len(kept)}, force=True)
        if ctx.cancelled():
            break
        fixed = count(system + template, tokenizer) + 200
        evidence, used = _evidence(items, available - fixed, tokenizer)
        prompt = template.format(evidence=evidence, max_cases=setting("tc.cases_per_section"), section=section,
                                 instructions=f"Additional instructions: {tc_set.instructions}" if tc_set.instructions else "")
        try:
            result = run("tc.generate", prompt, system=system, json_schema=prompts.TC_SCHEMA, job_id=ctx.job.pk,
                         should_stop=ctx.cancelled)
        except AIUnavailable as exc:
            raise Unavailable(str(exc)) from exc
        except AIFailed as exc:
            stats["section_errors"].append({"section": section, "error": str(exc)[:300]})
            continue
        for case in result.data.get("test_cases", []):
            stats["generated"] += 1
            problems = case_problems(case)
            if problems:
                stats["invalid"] += 1
                continue
            if is_duplicate(case, kept, setting("tc.duplicate_threshold")):
                stats["duplicates"] += 1
                continue
            sources = []
            for sid in case.get("source_ids") or []:
                digits = "".join(ch for ch in str(sid) if ch.isdigit())
                if digits and 1 <= int(digits) <= len(used) and used[int(digits) - 1] not in sources:
                    sources.append(used[int(digits) - 1])
            case["_sources"] = sources
            case["_section"] = section
            case["assumption"] = bool(case.get("assumption")) or not sources
            stats["assumptions"] += case["assumption"]
            kept.append(case)
    if not kept and stats["section_errors"]:
        raise RetryableError(f"no section produced test cases: {json.dumps(stats['section_errors'])[:500]}")
    _save(tc_set, kept, user)
    status = TCSet.Status.PARTIAL if stats["section_errors"] else TCSet.Status.READY
    stats["kept"] = len(kept)
    TCSet.objects.filter(pk=tc_set.pk).update(status=status, summary=stats)
    return {"set_id": tc_set.pk, **stats}


def _save(tc_set: TCSet, cases: list[dict], user) -> None:
    columns = tc_set.template.columns
    with transaction.atomic():
        tc_set.cases.all().delete()
        for n, case in enumerate(cases, 1):
            # Generated values are always kept (validation and traceability need them); the template decides
            # which of them are exported and in what order.
            fields = {key: str(case.get(key, "")).strip() for key in GENERATED_KEYS if key != "steps"}
            for col in columns:
                key = col["key"]
                if key in GENERATED_KEYS and key != "steps":
                    fields[key] = str(case.get(key, "")).strip()
                elif col.get("blank_unless_requested") and not tc_set.fill_priority:
                    fields[key] = ""
                else:
                    fields[key] = str(col.get("default", "")).replace("{section}", case["_section"][:200]) \
                        .replace("{user}", user.get_username())
            tc = TestCase.objects.create(tc_set=tc_set, ordinal=n, section=case["_section"][:500], fields=fields,
                                         steps=[{"action": s["action"].strip(), "expected": s["expected"].strip()}
                                                for s in case["steps"]],
                                         scenario_type=case.get("scenario_type", ""), assumption=case["assumption"])
            TestCaseSource.objects.bulk_create([TestCaseSource(
                test_case=tc, chunk_id=p.chunk_id, document_id=p.document_id, title=p.document_title[:300],
                version_no=p.version_no, locator=p.locator, section_path=p.section_path[:500]) for p in case["_sources"]])


__all__ = ["generate", "get_user_model"]
