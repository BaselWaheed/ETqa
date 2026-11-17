"""Checks the Phase 0 scripts' logic against a fake Ollama server. Real numbers come only from the target machine."""
import argparse
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "phase0"))
import bench_ollama  # noqa: E402
import ocr_check  # noqa: E402
import pdf_arabic_check  # noqa: E402

MODELS = ["qwen2.5:7b-instruct-q4_K_M", "qwen2.5:1.5b-instruct-q4_K_M", "bge-m3:latest"]


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [{"name": m} for m in MODELS]})
        elif self.path == "/api/ps":
            self._json({"models": [{"name": MODELS[0], "size": 5 * 2**30, "context_length": 8192}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            self._json({"embeddings": [[0.5] * 4 + [0.0] * 1020 for _ in body["input"]]})
            return
        if body.get("format"):
            self._json({"response": json.dumps({"intent": "greeting"}), "done": True})
            return
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for word in ("Test ", "scenarios"):
                self.wfile.write((json.dumps({"response": word, "done": False}) + "\n").encode())
            final = {"response": "", "done": True, "load_duration": 2e9, "prompt_eval_count": 1500,
                     "prompt_eval_duration": 30e9, "eval_count": 100, "eval_duration": 20e9}
            self.wfile.write((json.dumps(final) + "\n").encode())
            return
        self._json({"response": "", "done": True})


@pytest.fixture
def fake_ollama(tmp_path, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(bench_ollama, "HOST", f"http://127.0.0.1:{server.server_address[1]}")
    yield
    server.shutdown()


def test_generate_reports_ollama_counters(fake_ollama):
    out = bench_ollama.cmd_generate(argparse.Namespace(model=MODELS[0], contexts=[2048], runs=2, num_predict=16, threads=4))
    ctx = out["contexts"]["2048"]
    assert ctx["mean_prefill_tok_s"] == 50.0 and ctx["mean_gen_tok_s"] == 5.0
    assert all(r["first_token_s"] is not None for r in ctx["runs"])
    assert out["cold_load_s"] == 2.0 and out["loaded"][0]["size_mb"] == 5120


def test_embed_checks_dimensions(fake_ollama):
    out = bench_ollama.cmd_embed(argparse.Namespace(model="bge-m3", batch=[1, 4], chunks=8))
    assert out["dims"] == 1024 and out["l2_norm"] == 1.0 and set(out["batches"]) == {"1", "4"}


def test_structured_counts_valid_json(fake_ollama):
    out = bench_ollama.cmd_structured(argparse.Namespace(model=MODELS[1], n=10))
    assert out["valid_json"] == 10 and out["schema_valid"] == 10 and out["correct_label"] == 2


def test_missing_model_stops_with_pull_hint(fake_ollama):
    with pytest.raises(SystemExit, match="ollama pull qwen3-vl:4b"):
        bench_ollama.require("qwen3-vl:4b")


def test_prompts_differ_per_run_to_avoid_prompt_cache():
    assert bench_ollama.filler(500, 0).splitlines()[0] != bench_ollama.filler(500, 1).splitlines()[0]


def test_arabic_order_heuristic():
    logical = " ".join(["الفوترة", "الرصيد", "المشترك", "الخطأ"] * 10)
    reversed_text = " ".join(word[::-1] for word in logical.split())
    assert pdf_arabic_check.score(logical)["verdict"].startswith("logical")
    assert pdf_arabic_check.score(reversed_text)["verdict"].startswith("REVERSED")
    assert pdf_arabic_check.score("short")["verdict"] == "too little Arabic to judge"


def test_cer_ignores_diacritics_and_whitespace():
    ref = ocr_check.normalize("الرَّصِيد   غير كافٍ")
    assert ocr_check.normalize("الرصيد غير كاف") == ref
    assert ocr_check.levenshtein("kitten", "sitting") == 3
