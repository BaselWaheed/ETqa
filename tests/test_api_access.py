"""Cross-role API tests (Phase 1 exit gate)."""
import pytest

from apps.access.models import Collection
from apps.access.roles import ADMIN, QA_ENGINEER, REVIEWER, VIEWER
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


def test_unauthenticated_requests_are_denied(api, collections):
    for url in ("/api/v1/collections/", "/api/v1/me/", f"/api/v1/collections/{collections['billing'].id}/"):
        assert api().get(url).status_code == 403


@pytest.mark.parametrize("role,expected", [
    (QA_ENGINEER, {"billing"}), (VIEWER, {"billing"}), (REVIEWER, {"hr"}), (ADMIN, {"billing", "hr"}),
])
def test_collection_list_is_scoped(api, users, collections, role, expected):
    resp = api(users[role]).get("/api/v1/collections/")
    assert resp.status_code == 200
    assert {c["slug"] for c in resp.json()["results"]} == expected


def test_unreadable_collection_returns_404_not_403(api, users, collections):
    resp = api(users[VIEWER]).get(f"/api/v1/collections/{collections['hr'].id}/")
    assert resp.status_code == 404


@pytest.mark.parametrize("role", [REVIEWER, QA_ENGINEER, VIEWER])
def test_only_admin_creates_collections(api, users, role):
    resp = api(users[role]).post("/api/v1/collections/", {"name": "X", "slug": "x"}, format="json")
    assert resp.status_code == 403
    assert not Collection.objects.filter(slug="x").exists()


def test_admin_creates_collection_and_it_is_audited(api, users):
    resp = api(users[ADMIN]).post("/api/v1/collections/", {"name": "Network", "slug": "network"}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["access"] == "manage"
    event = AuditEvent.objects.get(action="access.collection_created")
    assert event.actor == users[ADMIN] and event.object_id == str(resp.json()["id"])


def test_grant_changes_access_and_is_audited(api, users, collections):
    hr = collections["hr"]
    assert api(users[VIEWER]).get(f"/api/v1/collections/{hr.id}/").status_code == 404
    resp = api(users[ADMIN]).post(f"/api/v1/collections/{hr.id}/grants/", {"group": VIEWER, "level": "read"}, format="json")
    assert resp.status_code == 201
    assert api(users[VIEWER]).get(f"/api/v1/collections/{hr.id}/").status_code == 200
    assert AuditEvent.objects.filter(action="access.grant_set", detail__group=VIEWER).exists()
    assert api(users[ADMIN]).delete(f"/api/v1/collections/{hr.id}/grants/{VIEWER}/").status_code == 204
    assert api(users[VIEWER]).get(f"/api/v1/collections/{hr.id}/").status_code == 404


@pytest.mark.parametrize("role", [REVIEWER, QA_ENGINEER, VIEWER])
def test_non_admin_cannot_change_grants(api, users, collections, role):
    url = f"/api/v1/collections/{collections['billing'].id}/grants/"
    assert api(users[role]).post(url, {"group": role, "level": "manage"}, format="json").status_code == 403
    assert api(users[role]).get(url).status_code == 403


def test_session_post_without_csrf_token_is_rejected(api, users):
    resp = api(users[ADMIN], csrf=True).post("/api/v1/collections/", {"name": "Y", "slug": "y"}, format="json")
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]


def test_me_shows_roles_and_only_language_is_editable(api, users):
    client = api(users[QA_ENGINEER])
    assert client.get("/api/v1/me/").json()["roles"] == [QA_ENGINEER]
    resp = client.patch("/api/v1/me/", {"preferred_language": "ar", "username": "hacker", "roles": ["Admin"]}, format="json")
    assert resp.status_code == 200
    users[QA_ENGINEER].refresh_from_db()
    assert users[QA_ENGINEER].preferred_language == "ar"
    assert users[QA_ENGINEER].username == "qa1"
    assert not users[QA_ENGINEER].groups.filter(name=ADMIN).exists()
