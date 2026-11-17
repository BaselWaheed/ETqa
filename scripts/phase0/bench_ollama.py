"""Phase 0 benchmarks against the local Ollama server (U1, U2, U7, U8, U13 and the ADR-09 vision check).

Pull the models first, e.g.:
    ollama pull qwen2.5:7b-instruct-q4_K_M
    ollama pull qwen2.5:1.5b-instruct-q4_K_M
    ollama pull bge-m3
    ollama pull qwen3-vl:4b          (tag to be confirmed in the Ollama library)

Usage:
    python scripts/phase0/bench_ollama.py generate --model qwen2.5:7b-instruct-q4_K_M
    python scripts/phase0/bench_ollama.py embed
    python scripts/phase0/bench_ollama.py cancel --model qwen2.5:7b-instruct-q4_K_M
    python scripts/phase0/bench_ollama.py structured --model qwen2.5:1.5b-instruct-q4_K_M --n 200
    python scripts/phase0/bench_ollama.py vision --image sample_diagram.png
    python scripts/phase0/bench_ollama.py all
Results go to phase0_report/ollama_<command>.json. Standard library only.
Close other heavy applications first; numbers measured with a browser full of tabs are not representative.
"""
import argparse
import base64
import http.client
import json
import math
import pathlib
import time
import urllib.parse

from common import mean, memory_mb, save

HOST = "http://127.0.0.1:11434"
MAIN, SLM, EMBED, VISION = "qwen2.5:7b-instruct-q4_K_M", "qwen2.5:1.5b-instruct-q4_K_M", "bge-m3", "qwen3-vl:4b"

FILLER_EN = ("The billing adapter receives a ChargeRequest from the order service, validates the MSISDN format, "
             "checks the subscriber balance through getSubscriberProfile, and returns ERR_4012 when the balance "
             "is insufficient. Retries are attempted three times with exponential backoff before the request is "
             "moved to the dead-letter queue. ")
FILLER_AR = ("يستقبل محول الفوترة طلب الخصم من خدمة الطلبات، ويتحقق من صيغة رقم MSISDN، ثم يتحقق من رصيد المشترك "
             "عبر getSubscriberProfile، ويعيد الخطأ ERR_4012 عندما يكون الرصيد غير كافٍ. ")


# ---------------------------------------------------------------- HTTP helpers
def _conn(timeout: float = 600) -> http.client.HTTPConnection:
    url = urllib.parse.urlparse(HOST)
    return http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)


def post(path: str, body: dict, timeout: float = 600) -> dict:
    conn = _conn(timeout)
    conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"{path} -> HTTP {resp.status}: {data[:300]!r}")
    return json.loads(data)


def get(path: str) -> dict:
    conn = _conn(10)
    conn.request("GET", path)
    data = conn.getresponse().read()
    conn.close()
    return json.loads(data)


def loaded_models() -> list[dict]:
    return [{"name": m["name"], "size_mb": m.get("size", 0) // 2**20, "context": m.get("context_length")}
            for m in get("/api/ps").get("models", [])]


def require(model: str) -> None:
    names = {m["name"] for m in get("/api/tags").get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        raise SystemExit(f"Model {model!r} is not pulled. Run: ollama pull {model}")


def unload(model: str) -> None:
    try:
        post("/api/generate", {"model": model, "keep_alive": 0}, timeout=60)
    except RuntimeError:
        pass


def stream_generate(body: dict) -> dict:
    """Streams /api/generate and returns wall-clock timings plus Ollama's own counters."""
    started = time.perf_counter()
    conn = _conn()
    conn.request("POST", "/api/generate", json.dumps({**body, "stream": True}), {"Content-Type": "application/json"})
    resp = conn.getresponse()
    if resp.status != 200:
        raise RuntimeError(f"generate -> HTTP {resp.status}: {resp.read()[:300]!r}")
    first_token, final, text = None, {}, []
    while True:
        line = resp.readline()
        if not line:
            break
        chunk = json.loads(line)
        if chunk.get("response"):
            text.append(chunk["response"])
            if first_token is None:
                first_token = time.perf_counter() - started
        if chunk.get("done"):
            final = chunk
            break
    conn.close()
    ns = 1e9
    prompt_n, gen_n = final.get("prompt_eval_count", 0), final.get("eval_count", 0)
    return {
        "wall_s": round(time.perf_counter() - started, 2),
        "first_token_s": round(first_token, 2) if first_token else None,
        "load_s": round(final.get("load_duration", 0) / ns, 2),
        "prompt_tokens": prompt_n,
        "prefill_tok_s": round(prompt_n / (final["prompt_eval_duration"] / ns), 1) if final.get("prompt_eval_duration") else None,
        "output_tokens": gen_n,
        "gen_tok_s": round(gen_n / (final["eval_duration"] / ns), 2) if final.get("eval_duration") else None,
        "text_head": "".join(text)[:120],
    }


def filler(target_tokens: int, run: int) -> str:
    # ~3 characters per token for this mixed text; the real count is read back from Ollama.
    block = FILLER_EN + FILLER_AR
    body = (block * (int(target_tokens * 3.0) // len(block) + 1))[: int(target_tokens * 3.0)]
    # A unique first line defeats Ollama's prompt cache so every run measures a cold prefill.
    return f"Request {run}-{time.time_ns()}.\nList the main test scenarios in this documentation:\n{body}"


# ---------------------------------------------------------------- commands
def cmd_generate(args) -> dict:
    require(args.model)
    options = {"temperature": 0, "num_predict": args.num_predict}
    if args.threads:
        options["num_thread"] = args.threads
    unload(args.model)
    mem_before = memory_mb()
    cold = stream_generate({"model": args.model, "prompt": "Say OK.", "options": {**options, "num_predict": 2},
                            "keep_alive": "10m"})
    result = {"model": args.model, "threads": args.threads, "cold_load_s": cold["load_s"],
              "memory_before_load": mem_before, "memory_after_load": memory_mb(), "loaded": loaded_models(), "contexts": {}}
    print(f"cold load {cold['load_s']} s")
    for ctx in args.contexts:
        runs = []
        for i in range(args.runs):
            r = stream_generate({"model": args.model, "prompt": filler(int(ctx * 0.75), i),
                                 "options": {**options, "num_ctx": ctx}, "keep_alive": "10m"})
            runs.append(r)
            print(f"ctx {ctx} run {i + 1}: prompt {r['prompt_tokens']} tok, first token {r['first_token_s']} s, "
                  f"prefill {r['prefill_tok_s']} tok/s, gen {r['gen_tok_s']} tok/s, total {r['wall_s']} s")
        result["contexts"][str(ctx)] = {
            "runs": runs,
            "mean_first_token_s": mean([r["first_token_s"] for r in runs]),
            "mean_prefill_tok_s": mean([r["prefill_tok_s"] for r in runs]),
            "mean_gen_tok_s": mean([r["gen_tok_s"] for r in runs]),
            "mean_wall_s": mean([r["wall_s"] for r in runs]),
        }
        result["contexts"][str(ctx)]["loaded"] = loaded_models()
    result["memory_end"] = memory_mb()
    return result


def cmd_embed(args) -> dict:
    require(args.model)
    texts = [(FILLER_EN if i % 2 else FILLER_AR) * 3 + f" #{i}" for i in range(args.chunks)]
    post("/api/embed", {"model": args.model, "input": ["warm-up"]})
    vec = post("/api/embed", {"model": args.model, "input": [texts[0]]})["embeddings"][0]
    result = {"model": args.model, "dims": len(vec), "l2_norm": round(math.sqrt(sum(v * v for v in vec)), 4),
              "batches": {}, "loaded": loaded_models()}
    print(f"dims {result['dims']} (expected 1024), L2 norm {result['l2_norm']}")
    for size in args.batch:
        started = time.perf_counter()
        for i in range(0, len(texts), size):
            post("/api/embed", {"model": args.model, "input": texts[i:i + size]})
        elapsed = time.perf_counter() - started
        result["batches"][str(size)] = {"chunks_per_s": round(len(texts) / elapsed, 2), "seconds": round(elapsed, 1)}
        print(f"batch {size}: {result['batches'][str(size)]['chunks_per_s']} chunks/s")
    return result


def cmd_cancel(args) -> dict:
    """U13: does closing the HTTP stream stop generation? Measured by how long a tiny request waits afterwards."""
    require(args.model)
    tiny = {"model": args.model, "prompt": "Say OK.", "options": {"num_predict": 2, "temperature": 0}, "keep_alive": "10m"}
    stream_generate(tiny)  # make sure the model is loaded
    baseline = stream_generate(tiny)["wall_s"]
    conn = _conn()
    conn.request("POST", "/api/generate", json.dumps({"model": args.model, "stream": True, "keep_alive": "10m",
                                                     "prompt": "Write a very long, detailed test plan for a billing system.",
                                                     "options": {"num_predict": 1500, "temperature": 0}}),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    deadline = time.perf_counter() + args.read_seconds
    while time.perf_counter() < deadline and resp.readline():
        pass
    conn.close()  # the cancel under test
    after = stream_generate(tiny)["wall_s"]
    stopped = after < baseline + 5
    verdict = ("Generation appears to stop when the stream closes." if stopped else
               "Ollama kept generating after the stream closed; cancel must stay 'stop waiting'.")
    print(f"baseline tiny request {baseline} s, after cancel {after} s -> {verdict}")
    return {"model": args.model, "baseline_tiny_s": baseline, "tiny_after_cancel_s": after,
            "generation_stopped": stopped, "verdict": verdict}


INTENT_SAMPLES = [
    ("hello", "greeting"), ("مرحبا", "greeting"), ("What does ERR_4012 mean?", "documentation_question"),
    ("ما معنى الخطأ ERR_4012؟", "documentation_question"), ("Generate test cases for the refund flow", "test_generation"),
    ("اكتب حالات اختبار لعملية الاسترداد", "test_generation"), ("Analyze this log: timeout on getSubscriberProfile", "log_analysis"),
    ("حلل هذا السجل: انتهاء المهلة في getSubscriberProfile", "log_analysis"), ("How do I change my password?", "other"),
    ("Explain the retry policy of the billing adapter", "documentation_question"),
]
INTENT_SCHEMA = {"type": "object", "properties": {"intent": {"type": "string", "enum": [
    "greeting", "documentation_question", "test_generation", "log_analysis", "other"]}}, "required": ["intent"]}


def cmd_structured(args) -> dict:
    """U8: how often does the SLM return valid, schema-conforming JSON, and is the label right?"""
    require(args.model)
    valid = schema_ok = correct = 0
    durations = []
    for i in range(args.n):
        query, expected = INTENT_SAMPLES[i % len(INTENT_SAMPLES)]
        started = time.perf_counter()
        out = post("/api/generate", {"model": args.model, "stream": False, "format": INTENT_SCHEMA, "keep_alive": "10m",
                                     "options": {"temperature": 0, "num_predict": 40},
                                     "prompt": f"Classify the intent of this message. Message: {query}"})
        durations.append(time.perf_counter() - started)
        try:
            data = json.loads(out["response"])
            valid += 1
            if data.get("intent") in INTENT_SCHEMA["properties"]["intent"]["enum"]:
                schema_ok += 1
                correct += data["intent"] == expected
        except (ValueError, AttributeError):
            pass
    result = {"model": args.model, "n": args.n, "valid_json": valid, "schema_valid": schema_ok,
              "correct_label": correct, "mean_s": mean(durations)}
    print(result)
    return result


def cmd_vision(args) -> dict:
    """ADR-09: vision model under the exclusive-window sequence (unload text models, confirm, run, unload)."""
    require(args.model)
    for m in (args.main, args.slm):
        unload(m)
    still_loaded = [m["name"] for m in loaded_models()]
    image = base64.b64encode(pathlib.Path(args.image).read_bytes()).decode()
    mem_before = memory_mb()
    r = stream_generate({"model": args.model, "images": [image], "keep_alive": 0,
                         "prompt": args.prompt, "options": {"temperature": 0, "num_predict": 400}})
    result = {"model": args.model, "text_models_still_loaded_before_run": still_loaded,
              "memory_before": mem_before, **r, "memory_after": memory_mb()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    global HOST
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=HOST)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate"); g.add_argument("--model", default=MAIN)
    g.add_argument("--contexts", type=int, nargs="+", default=[2048, 4096, 8192])
    g.add_argument("--runs", type=int, default=3); g.add_argument("--num-predict", type=int, default=256)
    g.add_argument("--threads", type=int, default=None, help="num_thread; try the physical core count")
    e = sub.add_parser("embed"); e.add_argument("--model", default=EMBED)
    e.add_argument("--batch", type=int, nargs="+", default=[1, 8, 16, 32]); e.add_argument("--chunks", type=int, default=64)
    c = sub.add_parser("cancel"); c.add_argument("--model", default=MAIN); c.add_argument("--read-seconds", type=float, default=5)
    s = sub.add_parser("structured"); s.add_argument("--model", default=SLM); s.add_argument("--n", type=int, default=50)
    v = sub.add_parser("vision"); v.add_argument("--model", default=VISION); v.add_argument("--image", required=True)
    v.add_argument("--main", default=MAIN); v.add_argument("--slm", default=SLM)
    v.add_argument("--prompt", default="Describe this technical diagram: list each component and each connection. "
                                       "Keep identifiers exactly as written, including Arabic text.")
    sub.add_parser("all", help="generate (main + SLM), embed, cancel, structured")
    args = parser.parse_args()
    HOST = args.host

    commands = {"generate": cmd_generate, "embed": cmd_embed, "cancel": cmd_cancel,
                "structured": cmd_structured, "vision": cmd_vision}
    if args.command == "all":
        base = dict(contexts=[2048, 4096, 8192], runs=3, num_predict=256, threads=None)
        save("ollama_generate_main", cmd_generate(argparse.Namespace(model=MAIN, **base)))
        save("ollama_generate_slm", cmd_generate(argparse.Namespace(model=SLM, **{**base, "contexts": [2048]})))
        save("ollama_embed", cmd_embed(argparse.Namespace(model=EMBED, batch=[1, 8, 16, 32], chunks=64)))
        save("ollama_cancel", cmd_cancel(argparse.Namespace(model=MAIN, read_seconds=5)))
        save("ollama_structured", cmd_structured(argparse.Namespace(model=SLM, n=50)))
    else:
        save(f"ollama_{args.command}", commands[args.command](args))


if __name__ == "__main__":
    main()
