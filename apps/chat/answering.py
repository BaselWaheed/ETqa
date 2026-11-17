"""Builds the answer prompt from retrieved passages and checks the model's citations."""
from __future__ import annotations

import re

from apps.ai import prompts
from apps.ai.tokens import count
from apps.retrieval.services import Passage
from apps.sysconfig.services import get as setting

MARKER = re.compile(r"\[S(\d+)\]")
LANG_NAMES = {"ar": "Arabic", "en": "English", "mixed": "the same language as the question"}


def insufficient_text(lang: str) -> str:
    return setting("chat.insufficient_ar") if lang == "ar" else setting("chat.insufficient_en")


def evidence_block(passages: list[Passage], budget_tokens: int, tokenizer: str, fixed_tokens: int) -> tuple[str, list[Passage]]:
    """Adds passages in rank order while they fit; lowest-ranked are trimmed first (router step 3)."""
    parts, used, total = [], [], fixed_tokens
    for p in passages:
        where = ", ".join(x for x in (p.locator, p.section_path) if x)
        label = "machine-generated image description; " if "vision" in p.flags else ""
        entry = f"[S{len(used) + 1}] ({p.document_title} v{p.version_no}; {label}{where})\n{p.text}"
        cost = count(entry, tokenizer)
        if total + cost > budget_tokens:
            continue
        parts.append(entry)
        used.append(p)
        total += cost
    return "\n\n".join(parts), used


def build_prompts(question: str, lang: str, passages: list[Passage], history: list[dict], budget_tokens: int,
                  tokenizer: str) -> tuple[str, str, list[Passage]]:
    system = prompts.get("chat.answer.system").format(insufficient=insufficient_text(lang),
                                                      language=LANG_NAMES.get(lang, "English"))
    turns = history[-setting("chat.history_turns") * 2:]
    hist = "".join(f"{'User' if t.get('role') == 'user' else 'ETqa'}: {str(t.get('content', ''))[:1500]}\n" for t in turns)
    hist = f"PREVIOUS TURNS (context only):\n{hist}\n" if hist else ""
    template = prompts.get("chat.answer.user")
    fixed = count(system + template.format(evidence="", history=hist, question=question), tokenizer)
    evidence, used = evidence_block(passages, budget_tokens, tokenizer, fixed)
    return system, template.format(evidence=evidence, history=hist, question=question), used


def check_citations(answer: str, used: list[Passage], lang: str) -> tuple[str, str, list[tuple[str, Passage]]]:
    """Removes markers that do not match a supplied passage and classifies the evidence level."""
    if answer.strip().rstrip(".").strip() == insufficient_text(lang).rstrip(".").strip() or \
            insufficient_text("en").rstrip(".") in answer or insufficient_text("ar").rstrip(".") in answer:
        return insufficient_text(lang), "insufficient", []
    cited: dict[int, Passage] = {}

    def keep(match):
        n = int(match.group(1))
        if 1 <= n <= len(used):
            cited[n] = used[n - 1]
            return match.group(0)
        return ""

    cleaned = MARKER.sub(keep, answer).strip()
    level = "cited" if cited else "unsupported"
    return cleaned, level, [(f"S{n}", cited[n]) for n in sorted(cited)]
