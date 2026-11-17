"""Phase 5 retrieval: hybrid search, Arabic normalization, identifiers, and no cross-collection leakage."""
import pytest
from django.core.management import call_command

from apps.access.scope import build_scope
from apps.retrieval import text as textutil
from apps.retrieval import vectors
from apps.retrieval.models import Chunk, ChunkEmbedding, EmbeddingSpace
from apps.retrieval.services import search
from tests.conftest import fake_vector, run_jobs

pytestmark = pytest.mark.django_db

SECRET = "Salary bands for grade 7 are confidential and approved by the HR committee."


@pytest.fixture
def corpus(ollama, ai_models, ingest):
    billing = ingest("billing.txt", ("1 Charging\nThe billing adapter retries failed charges three times. "
                                     "Error ERR_4012 means insufficient balance.\n\n2 Refunds\nRefunds take five days.").encode())
    hr = ingest("hr.txt", f"1 Salaries\n{SECRET}\nRetries of salary payments follow the payroll calendar.".encode(),
                collection="hr")
    run_jobs("general")  # embeddings
    return {"billing": billing, "hr": hr}


def test_embeddings_created_and_space_active(corpus):
    space = EmbeddingSpace.objects.get(is_active=True)
    assert space.dims == 1024
    assert ChunkEmbedding.objects.filter(space=space).count() == Chunk.objects.count()
    corpus["billing"].refresh_from_db()
    assert corpus["billing"].embedded


@pytest.mark.parametrize("backend", ["array", "pgvector"])
def test_no_cross_collection_leakage(corpus, users, setting_override, backend):
    """Phase 5 gate: restricted text never comes back, through any signal or backend."""
    if backend == "pgvector":
        try:
            call_command("enable_pgvector")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"pgvector not installable here: {exc}")
    setting_override("retrieval.vector_backend", backend)
    hr_chunk = Chunk.objects.get(collection=corpus["hr"].document.collection)
    exact_hr_vector = ChunkEmbedding.objects.get(chunk=hr_chunk).vector
    for role in ("Viewer", "QA Engineer"):
        scope = build_scope(users[role])
        for query, qvec in [("salary bands grade 7 confidential", None), ("retries", None), ("anything", exact_hr_vector)]:
            result = search(query, scope, query_vector=qvec)
            assert result.vector_used
            assert all(p.collection_id in scope.readable for p in result.passages)
            assert SECRET not in " ".join(p.text for p in result.passages)
    reviewer = search("salary bands grade 7", build_scope(users["Reviewer"]))
    assert any(SECRET in p.text for p in reviewer.passages)


def test_identifier_search_finds_error_code(corpus, users):
    result = search("ERR_4012", build_scope(users["QA Engineer"]))
    assert result.passages and "ERR_4012" in result.passages[0].text
    assert "identifier" in result.passages[0].signals


def test_keyword_search_works_when_ai_is_down(corpus, users, monkeypatch):
    from apps.ai.health import reset_cache

    monkeypatch.setenv("ETQA_OLLAMA_URL", "http://127.0.0.1:9")
    reset_cache()
    result = search("refunds five days", build_scope(users["QA Engineer"]))
    assert not result.vector_used and result.passages and "semantic search skipped" in result.notes[0]


def test_collection_filter_narrows_but_never_widens(corpus, users, collections):
    scope = build_scope(users["Viewer"])
    assert search("salary", scope, collection_ids=[collections["hr"].id]).passages == []


def test_array_backend_refuses_oversized_scope(corpus, users, setting_override):
    setting_override("retrieval.vector_backend", "array")
    setting_override("retrieval.array_max_candidates", 1)
    result = search("billing retries", build_scope(users["Admin"]))
    assert any("install pgvector" in n for n in result.notes)


def test_arabic_normalization():
    assert textutil.normalize("الإجراءات أُعتمدت في المرحلة") == textutil.normalize("الاجراءات اعتمدت في المرحله")
    assert textutil.normalize("رقم ١٢٣ ـــ") == "رقم 123"
    assert textutil.detect_language("ما معنى الخطأ ERR_4012 في الفوترة") == "ar"
    assert textutil.identifiers("call getSubscriberProfile, got ERR_4012 for txn 7f9c2b1e-1111-2222-3333-444455556666") == [
        "getSubscriberProfile", "ERR_4012", "7f9c2b1e-1111-2222-3333-444455556666"]


def test_arabic_spelling_variants_match(ollama, ai_models, ingest, users):
    ingest("ar.txt", "١ الإسترداد\nيتم إسترداد المبلغ خلال خمسة أيام عمل.".encode())
    result = search("استرداد المبلغ", build_scope(users["QA Engineer"]))
    assert result.passages and "fts" in result.passages[0].signals


def test_vector_similarity_floor(corpus, users, setting_override):
    setting_override("retrieval.min_vector_similarity", 0.99)
    result = search("zzz qqq unrelated", build_scope(users["QA Engineer"]), query_vector=fake_vector("zzz qqq"))
    assert result.passages == []


def test_backend_auto_detection():
    assert vectors.backend_name() in ("array", "pgvector")
