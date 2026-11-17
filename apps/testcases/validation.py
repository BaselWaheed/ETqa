"""Deterministic checks on generated test cases (Python, not the model)."""
from __future__ import annotations

import difflib
import re

_WS = re.compile(r"\s+")


def case_problems(case: dict) -> list[str]:
    problems = []
    if not str(case.get("name", "")).strip():
        problems.append("missing name")
    if not str(case.get("objective", "")).strip():
        problems.append("missing objective")
    steps = case.get("steps") or []
    if not steps:
        problems.append("no steps")
    for i, step in enumerate(steps, 1):
        if not str(step.get("action", "")).strip():
            problems.append(f"step {i} has no action")
        if not str(step.get("expected", "")).strip():
            problems.append(f"step {i} has no expected result")
    if not str(case.get("expected_result", "")).strip():
        problems.append("missing overall expected result")
    return problems


def _signature(case: dict) -> str:
    steps = " ".join(str(s.get("action", "")) for s in case.get("steps") or [])
    return _WS.sub(" ", f"{case.get('name', '')} {steps}".lower()).strip()


def is_duplicate(case: dict, kept: list[dict], threshold: float) -> bool:
    sig = _signature(case)
    return any(difflib.SequenceMatcher(None, sig, _signature(k)).ratio() >= threshold for k in kept)
