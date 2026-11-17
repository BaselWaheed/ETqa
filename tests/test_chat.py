"""Phase 5 chat: grounded answers, citation checks, insufficient evidence, unsaved chats, AI outages."""
import pytest

from apps.chat.models import Citation, Conversation, Feedback, Message
from apps.jobs.models import Job
from tests.conftest import run_jobs

pytestmark = pytest.mark.django_db
HR_SECRET = "Salary bands for grade 7 are confidential."


@pytest.fixture
def docs(ollama, ai_models, ingest):
    ingest("billing.txt", ("1 Retry policy\nThe billing adapter retries failed charges three times with exponential "
                           "backoff. Error ERR_4012 means insufficient balance.").encode(), title="Billing guide")
    ingest("hr.txt", f"1 Salaries\n{HR_SECRET} Retry rules for salary payments are monthly.".encode(), collection="hr")
    run_jobs("general")


def ask(api, user, **body):
    resp = api(user).post("/api/v1/chat/ask/", body, format="json")
    return resp


def test_cited_answer_saved_with_citations(api, users, docs, ollama):
    ollama.generate_reply = lambda body: "Failed charges are retried three times [S1]. Unknown claim [S9]."
    resp = ask(api, users["QA Engineer"], question="How many times are failed charges retried?")
    assert resp.status_code == 202 and resp.json()["saved"] and resp.json()["ai_available"]
    run_jobs("inference")
    message = Message.objects.get(pk=resp.json()["message_id"])
    assert message.evidence == "cited" and "[S1]" in message.content and "[S9]" not in message.content
    citation = Citation.objects.get(message=message)
    assert citation.title == "Billing guide" and citation.locator == "Document" and citation.section_path == "1 Retry policy"
    job = api(users["QA Engineer"]).get(f"/api/v1/jobs/{resp.json()['job_id']}/").json()
    assert job["status"] == "completed" and job["result"]["citations"][0]["marker"] == "S1"


def test_restricted_text_never_reaches_the_prompt(api, users, docs, ollama):
    ask(api, users["Viewer"], question="What are the salary bands and retry rules?")
    run_jobs("inference")
    assert ollama.prompts(), "the model should have been called with billing evidence"
    assert all(HR_SECRET not in p for p in ollama.prompts())


def test_no_evidence_means_no_model_call(api, users, docs, ollama):
    before = len(ollama.prompts())
    resp = ask(api, users["QA Engineer"], question="zebra giraffe quantum")
    run_jobs("inference")
    result = api(users["QA Engineer"]).get(f"/api/v1/jobs/{resp.json()['job_id']}/").json()["result"]
    assert result["evidence"] == "insufficient"
    assert result["answer"].startswith("The available documentation does not provide sufficient information")
    assert len(ollama.prompts()) == before


def test_arabic_question_gets_arabic_rules_and_message(api, users, docs, ollama):
    ollama.generate_reply = lambda body: "الوثائق المتاحة لا توفر معلومات كافية للإجابة عن هذا السؤال."
    resp = ask(api, users["QA Engineer"], question="ما سياسة إعادة المحاولة في billing adapter؟")
    run_jobs("inference")
    system = [c["body"]["system"] for c in ollama.calls if c["body"].get("system")][-1]
    assert "Answer in Arabic" in system
    result = api(users["QA Engineer"]).get(f"/api/v1/jobs/{resp.json()['job_id']}/").json()["result"]
    assert result["evidence"] == "insufficient" and result["answer"].startswith("الوثائق المتاحة")


def test_answer_without_valid_citations_is_marked_unsupported(api, users, docs, ollama):
    ollama.generate_reply = lambda body: "Charges are retried five times."
    resp = ask(api, users["QA Engineer"], question="How are failed charges retried?")
    run_jobs("inference")
    assert Message.objects.get(pk=resp.json()["message_id"]).evidence == "unsupported"


def test_viewer_chat_is_not_saved_and_cleared_after_delivery(api, users, docs, ollama):
    resp = ask(api, users["Viewer"], question="How are failed charges retried?",
               history=[{"role": "user", "content": "earlier question"}])
    body = resp.json()
    assert body["saved"] is False and body["conversation_id"] is None
    assert not Conversation.objects.filter(user=users["Viewer"]).exists()
    run_jobs("inference")
    assert "earlier question" in ollama.prompts()[-1]  # history sent by the page is used
    first = api(users["Viewer"]).get(f"/api/v1/jobs/{body['job_id']}/").json()
    assert first["result"]["answer"]
    job = Job.objects.get(pk=body["job_id"])
    assert job.ephemeral and job.payload == {} and job.result == {}
    assert api(users["Viewer"]).get(f"/api/v1/jobs/{body['job_id']}/").json()["result"] == {}


def test_greeting_answered_without_a_job(api, users, ai_models):
    resp = ask(api, users["QA Engineer"], question="مرحبا")
    assert resp.status_code == 200 and "immediate" in resp.json() and not Job.objects.exists()


def test_question_queues_while_ai_is_down(api, users, ollama_down, ai_models):
    resp = ask(api, users["QA Engineer"], question="How are charges retried?")
    assert resp.status_code == 202 and resp.json()["ai_available"] is False
    assert run_jobs("inference") == []
    assert Job.objects.get(pk=resp.json()["job_id"]).status == "queued"


def test_follow_up_uses_conversation_history(api, users, docs, ollama):
    first = ask(api, users["QA Engineer"], question="How are failed charges retried?")
    run_jobs("inference")
    ask(api, users["QA Engineer"], question="And what does ERR_4012 mean?", conversation_id=first.json()["conversation_id"])
    run_jobs("inference")
    assert "How are failed charges retried?" in ollama.prompts()[-1]
    detail = api(users["QA Engineer"]).get(f"/api/v1/chat/conversations/{first.json()['conversation_id']}/").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert api(users["Reviewer"]).get(f"/api/v1/chat/conversations/{first.json()['conversation_id']}/").status_code == 404


def test_feedback_capture(api, users, docs, ollama):
    resp = ask(api, users["QA Engineer"], question="How are failed charges retried?")
    run_jobs("inference")
    url = f"/api/v1/chat/messages/{resp.json()['message_id']}/feedback/"
    assert api(users["QA Engineer"]).post(url, {"rating": -1, "comment": "missing backoff detail"}, format="json").status_code == 201
    assert Feedback.objects.get().rating == -1
    assert api(users["Reviewer"]).post(url, {"rating": 1}, format="json").status_code == 404  # not their message
    assert api(users["QA Engineer"]).post(url, {"rating": 5}, format="json").status_code == 400


def test_streamed_draft_is_written_to_progress(api, users, docs, ollama, setting_override):
    setting_override("jobs.progress_interval_seconds", 0)
    ollama.generate_reply = lambda body: "A long streamed answer that arrives in several pieces [S1]."
    resp = ask(api, users["QA Engineer"], question="How are failed charges retried?")
    run_jobs("inference")
    job = Job.objects.get(pk=resp.json()["job_id"])
    assert job.progress["stage"] == "generating" and job.progress["draft"].endswith("[S1].")


def test_access_removed_after_asking_is_honoured(api, users, docs, ollama, roles):
    resp = ask(api, users["Viewer"], question="How are failed charges retried?")
    users["Viewer"].groups.remove(roles["Viewer"])
    run_jobs("inference")
    result = Job.objects.get(pk=resp.json()["job_id"]).result
    assert result["evidence"] == "insufficient" and result["citations"] == []
