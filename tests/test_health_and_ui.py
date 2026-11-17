import pytest
from django.db import DatabaseError

from apps.access.roles import ADMIN, QA_ENGINEER, VIEWER

pytestmark = pytest.mark.django_db


def test_public_health_is_minimal(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


def test_public_health_reports_503_when_database_fails(client, monkeypatch):
    from apps.ops import views

    monkeypatch.setattr(views, "check_database", lambda: {"status": "down", "error": "OperationalError"})
    resp = client.get("/health")
    assert resp.status_code == 503 and resp.json()["database"] == "down"
    assert "OperationalError" not in resp.content.decode()  # no error detail to anonymous callers


def test_admin_health_details(api, users):
    body = api(users[ADMIN]).get("/api/v1/ops/health/").json()
    assert body["database"]["status"] == "ok"
    assert body["migrations"] == {"status": "ok", "pending": 0}
    assert body["extensions"]["pg_trgm"]


@pytest.mark.parametrize("role", [QA_ENGINEER, VIEWER])
def test_admin_health_forbidden_for_others(api, users, role):
    assert api(users[role]).get("/api/v1/ops/health/").status_code == 403


def test_home_requires_login(client):
    resp = client.get("/")
    assert resp.status_code == 302 and "/accounts/login/" in resp["Location"]


def test_home_lists_only_readable_collections(client, users, collections):
    client.force_login(users[VIEWER])
    html = client.get("/").content.decode()
    assert "Billing" in html and "HR" not in html and "Old" not in html


def test_arabic_preference_renders_rtl(client, users):
    user = users[QA_ENGINEER]
    user.preferred_language = "ar"
    user.save()
    client.force_login(user)
    html = client.get("/").content.decode()
    assert 'dir="rtl"' in html and 'lang="ar"' in html and "مجموعاتك" in html


def test_login_page_language_cookie(client):
    client.cookies["etqa_lang"] = "ar"
    html = client.get("/accounts/login/").content.decode()
    assert 'dir="rtl"' in html and "تسجيل الدخول" in html


def test_admin_link_only_for_admins(client, users):
    client.force_login(users[VIEWER])
    assert "/admin/" not in client.get("/").content.decode()
    client.force_login(users[ADMIN])
    assert "/admin/" in client.get("/").content.decode()


@pytest.mark.parametrize("path", ["/chat/", "/documents/", "/testcases/"])
def test_app_pages_render_for_every_role(client, users, path):
    for role in ("Admin", "Reviewer", "QA Engineer", "Viewer"):
        client.force_login(users[role])
        assert client.get(path).status_code == 200


def test_viewer_sees_unsaved_chat_notice_and_no_upload(client, users):
    client.force_login(users["Viewer"])
    assert "Your chats are not saved" in client.get("/chat/").content.decode()
    assert "You cannot upload to any collection." in client.get("/documents/").content.decode()
    assert 'href="/testcases/"' not in client.get("/chat/").content.decode()


def test_page_config_lists_only_readable_collections(client, users, collections):
    client.force_login(users["Viewer"])
    html = client.get("/chat/").content.decode()
    assert "Billing" in html and '"HR"' not in html


def test_admin_health_includes_queue_and_ai(api, users, ollama, ai_models):
    body = api(users["Admin"]).get("/api/v1/ops/health/").json()
    assert body["ai"]["ollama"] == "ok" and any(m["key"] == "main-llm" and m["pulled"] for m in body["ai"]["models"])
    assert set(body["queue"]["queues_without_worker"]) == {"general", "inference"}
