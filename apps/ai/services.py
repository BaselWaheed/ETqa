"""Public interface of the AI module: ai.run() for generation, ai.embed() for vectors (section 5).
Business modules never see model names; they ask for a task."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from apps.sysconfig.services import get as setting

from . import client, schema, tokens
from .health import ollama_available, reset_cache
from .models import AIExecution, AIModel, TaskRoute

log = logging.getLogger("etqa.ai")


class AIUnavailable(Exception):
    """No model could serve the task right now (runtime down, model missing or disabled)."""


class AIFailed(Exception):
    """Every allowed model failed or returned invalid output."""


@dataclass
class AIResult:
    text: str
    data: dict | list | None
    model_key: str
    prompt_tokens: int
    output_tokens: int
    attempts: list[dict] = field(default_factory=list)


def routes_for(task: str) -> list[TaskRoute]:
    routes = list(TaskRoute.objects.filter(task=task, model__enabled=True).select_related("model").order_by("priority"))
    if not routes:
        raise AIUnavailable(f"no enabled model is routed for task {task!r}")
    return routes if not routes[0].no_downgrade else routes[:1]


def primary_model(task: str) -> AIModel:
    return routes_for(task)[0].model


def budget(task: str, max_tokens: int | None = None) -> tuple[int, str]:
    """Tokens available for the prompt: context_limit - max_tokens - reserve. Also returns the tokenizer path."""
    route = routes_for(task)[0]
    ctx = min(route.model.context_limit, setting("chat.context_tokens"))
    out = max_tokens or route.max_tokens
    return int(ctx - out - ctx * setting("chat.reserve_ratio")), route.model.tokenizer_path


def _record(task, model, job_id, est, gen: client.Generation | None, outcome, error="") -> None:
    AIExecution.objects.create(task=task, model_key=model.key, job_id=job_id, prompt_tokens_est=est,
                               prompt_tokens=gen.prompt_tokens if gen else 0, output_tokens=gen.output_tokens if gen else 0,
                               load_ms=gen.load_ms if gen else 0, total_ms=gen.total_ms if gen else 0,
                               first_token_ms=gen.first_token_ms if gen else None, outcome=outcome, error_code=error)


def run(task: str, prompt: str, *, system: str = "", json_schema: dict | None = None, job_id: int | None = None,
        on_text: Callable[[str], None] | None = None, should_stop: Callable[[], bool] | None = None,
        images: list[str] | None = None, max_tokens: int | None = None) -> AIResult:
    """Router steps 2 and 4-7: route, execute, validate, fall back, record. Never returns unvalidated output."""
    if not ollama_available():
        raise AIUnavailable("the AI service is not reachable")
    attempts: list[dict] = []
    for route in routes_for(task):
        model = route.model
        options = {"temperature": route.temperature, "num_predict": max_tokens or route.max_tokens,
                   "num_ctx": min(model.context_limit, setting("chat.context_tokens"))}
        if model.num_thread:
            options["num_thread"] = model.num_thread
        est = tokens.count(system + prompt, model.tokenizer_path)
        for attempt in (1, 2):  # one retry on the same model, then the next route
            gen = None
            try:
                gen = client.generate(model.runtime_name, prompt, system=system, options=options,
                                      keep_alive=model.keep_alive, timeout=model.timeout_s, fmt=json_schema,
                                      on_text=on_text, should_stop=should_stop, images=images)
                data = None
                if json_schema is not None:
                    data = json.loads(gen.text)
                    problems = schema.errors(data, json_schema)
                    if problems:
                        raise client.ModelError("invalid_output", "; ".join(problems[:5]))
                _record(task, model, job_id, est, gen, "ok")
                if gen.prompt_tokens and est and abs(gen.prompt_tokens - est) / gen.prompt_tokens > 0.25:
                    log.info("token estimate for %s off by >25%% (est %s, actual %s)", model.key, est, gen.prompt_tokens)
                return AIResult(gen.text, data, model.key, gen.prompt_tokens, gen.output_tokens, attempts)
            except (client.ModelError, json.JSONDecodeError) as exc:
                code = exc.code if isinstance(exc, client.ModelError) else "invalid_json"
                _record(task, model, job_id, est, gen, "error", code)
                attempts.append({"model": model.key, "attempt": attempt, "error": code})
                if code == "cancelled":
                    raise AIFailed("cancelled") from exc
                if code == "unavailable":
                    reset_cache()
                    raise AIUnavailable("the AI service stopped responding") from exc
                if code == "model_missing":
                    break  # no point retrying this model
    raise AIFailed(f"all models failed for {task}: {attempts}")


def embed(texts: list[str], *, task: str = "embed") -> tuple[list[list[float]], AIModel]:
    if not ollama_available():
        raise AIUnavailable("the AI service is not reachable")
    model = primary_model(task)
    try:
        vectors = client.embed(model.runtime_name, texts, keep_alive=model.keep_alive, timeout=model.timeout_s)
    except client.ModelError as exc:
        if exc.code == "unavailable":
            reset_cache()
            raise AIUnavailable(str(exc)) from exc
        raise AIFailed(exc.code) from exc
    if model.dims and any(len(v) != model.dims for v in vectors):
        raise AIFailed(f"{model.key} returned vectors that are not {model.dims}-dimensional")
    return vectors, model
