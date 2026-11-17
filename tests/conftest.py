import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.access.models import Collection, CollectionGrant
from apps.access.roles import ADMIN, QA_ENGINEER, REVIEWER, VIEWER
from apps.access.services import bootstrap_roles

PASSWORD = "Correct-Horse-Battery-42"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def roles(db):
    bootstrap_roles()
    return {name: Group.objects.get(name=name) for name in (ADMIN, REVIEWER, QA_ENGINEER, VIEWER)}


@pytest.fixture
def make_user(db, roles, django_user_model):
    def _make(username: str, role: str | None = None, **extra):
        user = django_user_model.objects.create_user(username=username, password=PASSWORD, **extra)
        if role:
            user.groups.add(roles[role])
        return user
    return _make


@pytest.fixture
def users(make_user):
    return {
        ADMIN: make_user("admin1", ADMIN, is_staff=True),
        REVIEWER: make_user("reviewer1", REVIEWER),
        QA_ENGINEER: make_user("qa1", QA_ENGINEER),
        VIEWER: make_user("viewer1", VIEWER),
    }


@pytest.fixture
def collections(db, roles):
    """Three collections: billing readable by QA + Viewer, hr restricted to Reviewer, archived inactive."""
    billing = Collection.objects.create(name="Billing", slug="billing")
    hr = Collection.objects.create(name="HR", slug="hr")
    archived = Collection.objects.create(name="Old", slug="old", is_active=False)
    CollectionGrant.objects.create(collection=billing, group=roles[QA_ENGINEER], level="read")
    CollectionGrant.objects.create(collection=billing, group=roles[VIEWER], level="read")
    CollectionGrant.objects.create(collection=hr, group=roles[REVIEWER], level="read")
    CollectionGrant.objects.create(collection=archived, group=roles[QA_ENGINEER], level="read")
    return {"billing": billing, "hr": hr, "archived": archived}


@pytest.fixture
def api():
    def _client(user=None, csrf=False):
        client = APIClient(enforce_csrf_checks=csrf)
        if user is not None:
            client.force_login(user)
        return client
    return _client


# ----------------------------------------------------------------------------------------------------------------
# Phases 2-6 helpers
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402

WORD = re.compile(r"\w+", re.UNICODE)


def fake_vector(text: str, dims: int = 1024) -> list[float]:
    """Deterministic bag-of-words vector: texts sharing words are similar."""
    vec = [0.0] * dims
    for word in WORD.findall(text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeOllamaState:
    def __init__(self):
        self.models = ["qwen2.5:7b-instruct-q4_K_M", "qwen2.5:1.5b-instruct-q4_K_M", "bge-m3", "qwen3-vl:4b"]
        self.loaded: list[str] = []
        self.calls: list[dict] = []
        self.unloads: list[str] = []
        self.refuse_unload: set[str] = set()
        self.generate_reply = lambda body: "ok [S1]"
        self.fail_models: set[str] = set()

    def prompts(self) -> list[str]:
        return [c["body"].get("system", "") + "\n" + c["body"].get("prompt", "")
                for c in self.calls if c["path"] == "/api/generate" and c["body"].get("prompt")]


def _make_handler(state: FakeOllamaState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/tags":
                self._json({"models": [{"name": m} for m in state.models]})
            elif self.path == "/api/ps":
                self._json({"models": [{"name": m} for m in state.loaded]})
            else:
                self._json({}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            state.calls.append({"path": self.path, "body": body})
            model = body.get("model")
            if self.path == "/api/embed":
                self._json({"embeddings": [fake_vector(t) for t in body["input"]]})
                return
            if model not in state.models:
                self._json({"error": "model not found"}, 404)
                return
            if body.get("keep_alive") == 0 and not body.get("prompt"):
                state.unloads.append(model)
                if model not in state.refuse_unload and model in state.loaded:
                    state.loaded.remove(model)
                self._json({"done": True})
                return
            if model not in state.loaded:
                state.loaded.append(model)
            if model in state.fail_models:
                self._json({"error": "simulated failure"}, 500)
                return
            text = state.generate_reply(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for i in range(0, len(text), 12):
                self.wfile.write((json.dumps({"response": text[i:i + 12], "done": False}) + "\n").encode())
            self.wfile.write((json.dumps({"response": "", "done": True, "prompt_eval_count": len(body.get("prompt", "")) // 3,
                                          "eval_count": len(text) // 3, "load_duration": 1e8}) + "\n").encode())
    return Handler


@pytest.fixture
def ollama(monkeypatch):
    from apps.ai.health import reset_cache

    state = FakeOllamaState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ETQA_OLLAMA_URL", f"http://127.0.0.1:{server.server_address[1]}")
    reset_cache()
    yield state
    server.shutdown()
    reset_cache()


@pytest.fixture
def ollama_down(monkeypatch):
    from apps.ai.health import reset_cache

    monkeypatch.setenv("ETQA_OLLAMA_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def ai_models(db):
    from django.core.management import call_command

    call_command("seed_ai_models", stdout=io.StringIO())


@pytest.fixture
def file_root(settings, tmp_path):
    settings.ETQA_FILE_ROOT = tmp_path / "files"
    return settings.ETQA_FILE_ROOT


@pytest.fixture
def setting_override():
    from apps.sysconfig.services import reset, set_value

    changed = []

    def _set(key, value):
        set_value(key, value)
        changed.append(key)
    yield _set
    for key in changed:
        reset(key)


def run_jobs(queue: str = "general", limit: int = 20) -> list:
    """Runs queued jobs synchronously, as a worker would, until none are claimable."""
    from apps.jobs.worker import run_one

    ran = []
    for _ in range(limit):
        job = run_one(queue, f"test-worker-{queue}")
        if job is None:
            break
        job.refresh_from_db()
        ran.append(job)
    return ran


def make_docx(blocks: list[tuple]) -> bytes:
    """blocks: ("h1", text) | ("h2", text) | ("p", text) | ("table", [[cells], ...])"""
    import docx

    document = docx.Document()
    for kind, value in blocks:
        if kind.startswith("h"):
            document.add_heading(value, level=int(kind[1]))
        elif kind == "p":
            document.add_paragraph(value)
        elif kind == "table":
            table = document.add_table(rows=0, cols=len(value[0]))
            for row in value:
                cells = table.add_row().cells
                for cell, text in zip(cells, row):
                    cell.text = text
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def make_text_pdf(pages: list[str]) -> bytes:
    """A minimal PDF with a real text layer (Helvetica, ASCII), one string per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        lines = text.splitlines() or [""]
        ops = ["BT /F1 11 Tf 50 780 Td 14 TL"] + [f"({ln.replace('(', '[').replace(')', ']')}) Tj T*" for ln in lines] + ["ET"]
        stream = "\n".join(ops)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content_id = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {content_id} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def upload_file(name: str, data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data)


@pytest.fixture
def ingest(users, collections, file_root, roles):
    """Uploads and ingests a file as the admin into a collection; returns the DocumentVersion."""
    from apps.access.scope import build_scope
    from apps.documents.services import upload

    def _ingest(name: str, data: bytes, collection="billing", title=""):
        admin = users["Admin"]
        version = upload(user=admin, scope=build_scope(admin), collection_id=collections[collection].id,
                         uploaded=upload_file(name, data), title=title)
        run_jobs("general")
        version.refresh_from_db()
        return version
    return _ingest
