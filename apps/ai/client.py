"""Minimal Ollama HTTP client (standard library). Only apps.ai talks to Ollama (ADR-01 rule 3)."""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable


class ModelError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def base_url() -> str:
    return os.environ.get("ETQA_OLLAMA_URL", "http://127.0.0.1:11434")


def _conn(timeout: float) -> http.client.HTTPConnection:
    url = urllib.parse.urlparse(base_url())
    return http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)


def _request(method: str, path: str, body: dict | None, timeout: float):
    try:
        conn = _conn(timeout)
        conn.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
        return conn, conn.getresponse()
    except (OSError, http.client.HTTPException) as exc:
        raise ModelError("unavailable", str(exc)) from exc


def call_json(method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    conn, resp = _request(method, path, body, timeout)
    try:
        data = resp.read()
    except (OSError, http.client.HTTPException) as exc:
        raise ModelError("timeout", str(exc)) from exc
    finally:
        conn.close()
    if resp.status == 404:
        raise ModelError("model_missing", data[:200].decode("utf-8", "replace"))
    if resp.status != 200:
        raise ModelError(f"http_{resp.status}", data[:200].decode("utf-8", "replace"))
    return json.loads(data)


@dataclass
class Generation:
    text: str
    prompt_tokens: int
    output_tokens: int
    load_ms: int
    total_ms: int
    first_token_ms: int | None


def generate(model: str, prompt: str, *, system: str = "", options: dict, keep_alive: str, timeout: float,
             fmt: dict | None = None, on_text: Callable[[str], None] | None = None,
             should_stop: Callable[[], bool] | None = None, images: list[str] | None = None) -> Generation:
    """Streams a generation. on_text receives the text so far; should_stop() closes the stream (cancel)."""
    body = {"model": model, "prompt": prompt, "system": system, "options": options, "keep_alive": keep_alive,
            "stream": True}
    if fmt is not None:
        body["format"] = fmt
    if images:
        body["images"] = images
    started = time.perf_counter()
    conn, resp = _request("POST", "/api/generate", body, timeout)
    if resp.status != 200:
        detail = resp.read()[:200].decode("utf-8", "replace")
        conn.close()
        raise ModelError("model_missing" if resp.status == 404 else f"http_{resp.status}", detail)
    parts: list[str] = []
    first = None
    final: dict = {}
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            chunk = json.loads(line)
            if chunk.get("error"):
                raise ModelError("runtime_error", str(chunk["error"])[:200])
            if chunk.get("response"):
                if first is None:
                    first = int((time.perf_counter() - started) * 1000)
                parts.append(chunk["response"])
                if on_text:
                    on_text("".join(parts))
            if chunk.get("done"):
                final = chunk
                break
            if should_stop and should_stop():
                raise ModelError("cancelled")
    except (OSError, http.client.HTTPException) as exc:
        raise ModelError("timeout", str(exc)) from exc
    finally:
        conn.close()
    if not final:
        raise ModelError("incomplete", "stream ended without a final message")
    return Generation(text="".join(parts), prompt_tokens=final.get("prompt_eval_count", 0),
                      output_tokens=final.get("eval_count", 0), load_ms=int(final.get("load_duration", 0) / 1e6),
                      total_ms=int((time.perf_counter() - started) * 1000), first_token_ms=first)


def embed(model: str, texts: list[str], *, keep_alive: str, timeout: float) -> list[list[float]]:
    data = call_json("POST", "/api/embed", {"model": model, "input": texts, "keep_alive": keep_alive}, timeout)
    vectors = data.get("embeddings") or []
    if len(vectors) != len(texts):
        raise ModelError("bad_response", "embedding count mismatch")
    return vectors


def unload(model: str) -> None:
    call_json("POST", "/api/generate", {"model": model, "keep_alive": 0}, timeout=60)


def loaded() -> list[str]:
    return [m["name"] for m in call_json("GET", "/api/ps", timeout=10).get("models", [])]


def tags() -> list[str]:
    return [m["name"] for m in call_json("GET", "/api/tags", timeout=5).get("models", [])]
