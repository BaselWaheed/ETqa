import time

import pytest
from django.test import Client, override_settings

from apps.accounts.middleware import SESSION_STARTED_KEY
from apps.access.roles import QA_ENGINEER
from apps.audit.models import AuditEvent
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db
LOGIN = "/accounts/login/"


def test_login_success_is_audited(users):
    resp = Client().post(LOGIN, {"username": "qa1", "password": PASSWORD})
    assert resp.status_code == 302
    event = AuditEvent.objects.get(action="auth.login")
    assert event.actor == users[QA_ENGINEER] and event.ip == "127.0.0.1" and event.request_id


def test_failed_login_audits_username_but_never_password(users):
    Client().post(LOGIN, {"username": "qa1", "password": "wrong-password"})
    event = AuditEvent.objects.get(action="auth.login_failed")
    assert event.actor_label == "qa1"
    assert "wrong-password" not in str(event.detail) and "password" not in event.detail


@override_settings(LOGIN_MAX_FAILURES=3)
def test_account_locks_after_repeated_failures_even_with_correct_password(users):
    client = Client()
    for _ in range(3):
        client.post(LOGIN, {"username": "qa1", "password": "nope"})
    resp = client.post(LOGIN, {"username": "qa1", "password": PASSWORD})
    assert resp.status_code == 200
    assert "Too many failed sign-in attempts" in resp.content.decode()
    assert not AuditEvent.objects.filter(action="auth.login").exists()


@override_settings(LOGIN_MAX_FAILURES=3)
def test_lock_is_per_username(users):
    client = Client()
    for _ in range(3):
        client.post(LOGIN, {"username": "qa1", "password": "nope"})
    assert client.post(LOGIN, {"username": "viewer1", "password": PASSWORD}).status_code == 302


def test_absolute_session_timeout_logs_out(users):
    client = Client()
    client.force_login(users[QA_ENGINEER])
    assert client.get("/").status_code == 200
    session = client.session
    session[SESSION_STARTED_KEY] = time.time() - 9 * 3600  # older than the 8 h default
    session.save()
    resp = client.get("/")
    assert resp.status_code == 302 and resp["Location"].startswith(LOGIN)


def test_logout_requires_post(users):
    client = Client()
    client.force_login(users[QA_ENGINEER])
    assert client.get("/accounts/logout/").status_code == 405
    assert client.post("/accounts/logout/").status_code == 302
    assert AuditEvent.objects.filter(action="auth.logout").exists()


def test_session_cookie_flags():
    from django.conf import settings

    assert settings.SESSION_COOKIE_HTTPONLY and settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.SESSION_COOKIE_AGE == settings.SESSION_IDLE_MINUTES * 60 and settings.SESSION_SAVE_EVERY_REQUEST
