"""Phase 4: registry, routing, fallback, validation, availability, vision window."""
import json

import pytest

from apps.ai import services as ai
from apps.ai.models import AIExecution, AIModel, PromptTemplate, TaskRoute
from apps.ai.vision import VisionWindow, WindowNotReady
from apps.jobs.models import Job
from apps.jobs.services import enqueue
from tests.conftest import run_jobs

pytestmark = pytest.mark.django_db


def test_run_routes_task_to_registered_model(ollama, ai_models):
    ollama.generate_reply = lambda body: f"answer from {body['model']}"
    result = ai.run("chat.answer", "question")
    assert result.text == "answer from qwen2.5:7b-instruct-q4_K_M" and result.model_key == "main-llm"
    call = [c for c in ollama.calls if c["path"] == "/api/generate"][-1]["body"]
    assert call["keep_alive"] == "30m" and call["options"]["num_ctx"] == 8192


def test_model_change_is_configuration_only(ollama, ai_models):
    AIModel.objects.filter(key="main-llm").update(runtime_name="qwen2.5:1.5b-instruct-q4_K_M")
    ollama.generate_reply = lambda body: body["model"]
    assert ai.run("chat.answer", "q").text == "qwen2.5:1.5b-instruct-q4_K_M"


def test_fallback_to_next_route_after_retry(ollama, ai_models):
    TaskRoute.objects.create(task="chat.answer", model=AIModel.objects.get(key="slm"), priority=2)
    ollama.fail_models.add("qwen2.5:7b-instruct-q4_K_M")
    ollama.generate_reply = lambda body: "fallback answer"
    result = ai.run("chat.answer", "q")
    assert result.model_key == "slm" and [a["model"] for a in result.attempts] == ["main-llm", "main-llm"]
    assert AIExecution.objects.filter(model_key="main-llm", outcome="error").count() == 2


def test_no_downgrade_task_fails_instead_of_falling_back(ollama, ai_models):
    TaskRoute.objects.create(task="tc.generate", model=AIModel.objects.get(key="slm"), priority=2)
    ollama.fail_models.add("qwen2.5:7b-instruct-q4_K_M")
    with pytest.raises(ai.AIFailed):
        ai.run("tc.generate", "q")
    assert not AIExecution.objects.filter(model_key="slm").exists()


def test_schema_invalid_output_is_never_returned(ollama, ai_models):
    ollama.generate_reply = lambda body: json.dumps({"wrong": True})
    schema = {"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"]}
    with pytest.raises(ai.AIFailed):
        ai.run("intent.classify", "hello", json_schema=schema)
    ollama.generate_reply = lambda body: json.dumps({"intent": "greeting"})
    assert ai.run("intent.classify", "hello", json_schema=schema).data == {"intent": "greeting"}


def test_unavailable_runtime_raises_clear_error(ollama_down, ai_models):
    with pytest.raises(ai.AIUnavailable):
        ai.run("chat.answer", "q")


def test_inference_queue_waits_while_ollama_is_down(ollama_down, ai_models):
    job = enqueue("chat.answer", {"question": "x", "user_id": 1})
    assert run_jobs("inference") == []
    job.refresh_from_db()
    assert job.status == "queued" and job.attempts == 0


def test_disabled_model_is_not_used(ollama, ai_models):
    AIModel.objects.filter(key="main-llm").update(enabled=False)
    with pytest.raises(ai.AIUnavailable):
        ai.run("chat.answer", "q")


def test_execution_records_hold_no_text(ollama, ai_models):
    ai.run("chat.answer", "a very secret question")
    fields = {f.name for f in AIExecution._meta.fields}
    assert not fields & {"prompt", "text", "answer", "content"}


def test_budget_subtracts_output_and_reserve(ai_models):
    available, _ = ai.budget("chat.answer")
    assert available == int(8192 - 700 - 8192 * 0.08)


def test_prompt_override_from_database(ai_models):
    from apps.ai.prompts import get

    PromptTemplate.objects.create(task="vision.describe", version=2, body="Custom vision prompt", is_active=True)
    assert get("vision.describe") == "Custom vision prompt"


def test_embed_checks_dimensions(ollama, ai_models):
    vectors, model = ai.embed(["hello world"])
    assert len(vectors[0]) == 1024 and model.key == "embed-bge-m3"
    AIModel.objects.filter(key="embed-bge-m3").update(dims=768)
    with pytest.raises(ai.AIFailed):
        ai.embed(["hello"])


def test_vision_window_unloads_text_models_first(ollama, ai_models):
    ollama.loaded = ["qwen2.5:7b-instruct-q4_K_M", "qwen2.5:1.5b-instruct-q4_K_M"]
    window = VisionWindow()
    window.open(AIModel.objects.get(key="vision"))
    assert set(ollama.unloads) >= {"qwen2.5:7b-instruct-q4_K_M", "qwen2.5:1.5b-instruct-q4_K_M"}
    assert window.has_room()
    window.count = 3
    assert not window.has_room()  # capped at vision.window_max_jobs
    window.close()
    assert ollama.unloads[-1] == "qwen3-vl:4b"


def test_vision_window_aborts_if_unload_fails(ollama, ai_models):
    ollama.loaded = ["qwen2.5:7b-instruct-q4_K_M"]
    ollama.refuse_unload.add("qwen2.5:7b-instruct-q4_K_M")
    with pytest.raises(WindowNotReady):
        VisionWindow().open(AIModel.objects.get(key="vision"))


def test_vision_job_defers_while_chats_wait(ollama, ai_models, ingest):
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, "PNG")
    version = ingest("diagram.png", buf.getvalue())
    enqueue("chat.answer", {"question": "x", "user_id": 0}, priority=100)
    Job.objects.filter(kind="chat.answer").update(run_after="2100-01-01T00:00:00Z")  # waiting, not claimable now
    run_jobs("inference")
    vision = Job.objects.get(kind="vision.version")
    assert vision.status == "queued" and "chats are waiting" in vision.last_error and vision.attempts == 0
    Job.objects.filter(kind="chat.answer").delete()
    Job.objects.filter(pk=vision.pk).update(run_after="2000-01-01T00:00:00Z")
    ollama.generate_reply = lambda body: "Box A connects to Box B"
    run_jobs("inference")
    vision.refresh_from_db()
    assert vision.status == "completed" and vision.result["described"] == 1
    assert version.chunks.filter(flags__contains=["vision"], text__contains="Box A connects").exists()
