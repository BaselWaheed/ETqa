"""Phase 6: test case generation, validation, de-duplication, traceability, Excel export."""
import io
import json

import openpyxl
import pytest

from apps.testcases.models import DEFAULT_COLUMNS, TCSet, TCTemplate
from apps.testcases.models import TestCase as GeneratedCase
from tests.conftest import make_docx, run_jobs

pytestmark = pytest.mark.django_db

REQS = [("h1", "Refunds"), ("p", "A refund is allowed within 14 days when the order status is DELIVERED."),
        ("h2", "Limits"), ("p", "Refunds above 5000 EGP need supervisor approval. Error ERR_7001 is shown otherwise.")]


def case(name, sources=("S1",), steps=None, **extra):
    return {"name": name, "objective": f"Verify {name}", "preconditions": "Order exists",
            "steps": steps if steps is not None else [{"action": "Request a refund", "expected": "Refund accepted"}],
            "test_data": "order 123", "expected_result": "Refund processed", "scenario_type": "positive",
            "source_ids": list(sources), "assumption": False, **extra}


@pytest.fixture
def refund_doc(ollama, ai_models, ingest):
    version = ingest("refunds.docx", make_docx(REQS), title="Refund requirements")
    run_jobs("general")
    return version.document


def generate(api, user, **body):
    return api(user).post("/api/v1/testcases/sets/", body, format="json")


def test_generation_validates_dedupes_and_traces(api, users, refund_doc, ollama):
    cases = [case("Refund within 14 days"),
             case("Refund within 14 days "),                       # duplicate
             case("Broken case", steps=[]),                        # invalid: no steps
             case("Refund with invented rule", sources=("S42",)),  # unsupported source -> assumption
             case("Refund above 5000 EGP needs approval", sources=("S2",), scenario_type="boundary")]
    ollama.generate_reply = lambda body: json.dumps({"test_cases": cases})
    resp = generate(api, users["QA Engineer"], document=refund_doc.id)
    assert resp.status_code == 202
    run_jobs("inference")
    tc_set = TCSet.objects.get(pk=resp.json()["id"])
    assert tc_set.status == "ready"
    s = tc_set.summary
    assert s["duplicates"] >= 1 and s["invalid"] >= 1 and s["kept"] == GeneratedCase.objects.filter(tc_set=tc_set).count()
    invented = GeneratedCase.objects.get(tc_set=tc_set, fields__name="Refund with invented rule")
    assert invented.assumption and not invented.sources.exists()
    traced = GeneratedCase.objects.filter(tc_set=tc_set, fields__name="Refund within 14 days").first()
    assert not traced.assumption and traced.sources.first().title == "Refund requirements"
    assert traced.fields["priority"] == "" and traced.fields["component"] == ""
    assert traced.fields["folder"] == "Refunds" and traced.fields["status"] == "Draft"  # merged sections -> common parent


def test_excel_export_keeps_template_order(api, users, refund_doc, ollama):
    ollama.generate_reply = lambda body: json.dumps({"test_cases": [case("Refund within 14 days", steps=[
        {"action": "Open order 123", "expected": "Order shown"}, {"action": "Request refund", "expected": "Refund accepted"}])]})
    set_id = generate(api, users["QA Engineer"], document=refund_doc.id).json()["id"]
    run_jobs("inference")
    resp = api(users["QA Engineer"]).get(f"/api/v1/testcases/sets/{set_id}/export.xlsx")
    assert resp.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Test Cases"]
    header = [c.value for c in ws[1]]
    assert header == [c["label"] for c in DEFAULT_COLUMNS]
    row = {h: c.value for h, c in zip(header, ws[2])}
    assert row["Steps"] == "1. Open order 123\n2. Request refund"
    assert row["Expected Result"].startswith("1. Order shown\n2. Refund accepted\nOverall:")
    assert row["Priority"] is None and row["Component"] is None
    assert wb["Sources"]["D2"].value == "Refund requirements"


def test_custom_template_columns(api, users, refund_doc, ollama):
    tpl = TCTemplate.objects.create(name="ALM", columns=[{"key": "name", "label": "Test Name"},
                                                         {"key": "steps", "label": "Steps"},
                                                         {"key": "expected_result", "label": "Expected"},
                                                         {"key": "release", "label": "Release", "default": "R26.4"}])
    ollama.generate_reply = lambda body: json.dumps({"test_cases": [case("Refund window")]})
    set_id = generate(api, users["QA Engineer"], document=refund_doc.id, template=tpl.id).json()["id"]
    run_jobs("inference")
    wb = openpyxl.load_workbook(io.BytesIO(api(users["QA Engineer"]).get(f"/api/v1/testcases/sets/{set_id}/export.xlsx").content))
    assert [c.value for c in wb["Test Cases"][1]] == ["Test Name", "Steps", "Expected", "Release"]
    assert wb["Test Cases"]["D2"].value == "R26.4"


def test_generation_from_requirement_text(api, users, refund_doc, ollama, collections):
    ollama.generate_reply = lambda body: json.dumps({"test_cases": [case("Supervisor approval over 5000 EGP")]})
    resp = generate(api, users["QA Engineer"], collection=collections["billing"].id, requirement="refund supervisor approval")
    run_jobs("inference")
    assert TCSet.objects.get(pk=resp.json()["id"]).status == "ready"
    assert "5000 EGP" in ollama.prompts()[-1]


def test_permissions(api, users, refund_doc, collections):
    assert generate(api, users["Viewer"], document=refund_doc.id).status_code == 403
    assert generate(api, users["Reviewer"], document=refund_doc.id).status_code == 404  # cannot read billing
    assert generate(api, users["QA Engineer"], collection=collections["hr"].id, requirement="x").status_code == 403


def test_other_users_cannot_see_or_export_a_set(api, users, refund_doc, ollama):
    ollama.generate_reply = lambda body: json.dumps({"test_cases": [case("Refund window")]})
    set_id = generate(api, users["QA Engineer"], document=refund_doc.id).json()["id"]
    run_jobs("inference")
    assert api(users["Admin"]).get(f"/api/v1/testcases/sets/{set_id}/").status_code == 404
    assert api(users["Viewer"]).get(f"/api/v1/testcases/sets/{set_id}/export.xlsx").status_code == 403


def test_model_failure_on_every_section_retries_then_fails(api, users, refund_doc, ollama, setting_override):
    ollama.generate_reply = lambda body: "not json at all"
    resp = generate(api, users["QA Engineer"], document=refund_doc.id)
    run_jobs("inference")
    from apps.jobs.models import Job
    job = Job.objects.get(pk=resp.json()["job_id"])
    assert job.status in ("retrying", "failed") and "no section produced" in job.last_error
