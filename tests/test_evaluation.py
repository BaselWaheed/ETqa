import io
import json

import pytest
from django.core.management import call_command

from tests.conftest import run_jobs

pytestmark = pytest.mark.django_db


def test_evaluate_rag_reports_by_category(ollama, ai_models, ingest, users, tmp_path):
    ingest("billing.txt", b"1 Retry policy\nFailed charges are retried three times. ERR_4012 means insufficient balance.",
           title="Billing guide")
    run_jobs("general")
    ollama.generate_reply = lambda body: "They are retried three times [S1]."
    questions = tmp_path / "q.jsonl"
    questions.write_text("\n".join(json.dumps(q) for q in [
        {"id": "a", "category": "en", "question": "How many times are failed charges retried?", "expected_documents": ["Billing guide"]},
        {"id": "b", "category": "identifier", "question": "ERR_4012", "expected_documents": ["Billing guide"]},
        {"id": "c", "category": "en", "question": "zebra parking", "expected_documents": [], "should_be_insufficient": True},
    ]), encoding="utf-8")
    call_command("evaluate_rag", str(questions), "--user", "qa1", "--answers", stdout=io.StringIO())
    report = json.loads(questions.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["overall"]["hit_rate"] == 1.0 and report["overall"]["errors"] == 0
    assert report["by_category"]["identifier"]["mrr"] == 1.0
    assert report["overall"]["citation_correctness"] == 1.0 and report["overall"]["insufficient_correctness"] == 1.0
