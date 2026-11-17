import pathlib

import pytest
from django.db import connection, transaction
from django.db.utils import ProgrammingError

from apps.access.roles import VIEWER
from apps.audit.models import AuditEvent
from apps.audit.services import record

pytestmark = pytest.mark.django_db
GRANTS_SQL = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sql" / "02_app_grants.sql"


def test_record_rejects_sensitive_detail_keys():
    with pytest.raises(ValueError):
        record("test.action", password="x")
    with pytest.raises(ValueError):
        record("test.action", prompt="secret prompt")


def test_group_membership_changes_are_audited(users, roles):
    users[VIEWER].groups.remove(roles[VIEWER])
    event = AuditEvent.objects.get(action="access.user_groups_changed", object_id=str(users[VIEWER].pk),
                                  detail__change="remove")
    assert event.detail == {"change": "remove", "group_ids": [roles[VIEWER].pk]}


def test_request_id_header_is_returned_and_recorded(client, users):
    resp = client.post("/accounts/login/", {"username": "viewer1", "password": "bad"}, HTTP_X_REQUEST_ID="abcdef12345")
    assert resp["X-Request-ID"] == "abcdef12345"
    assert AuditEvent.objects.get(action="auth.login_failed").request_id == "abcdef12345"


def test_malformed_request_id_is_replaced(client):
    resp = client.get("/health", HTTP_X_REQUEST_ID="<script>")
    assert resp["X-Request-ID"] != "<script>" and len(resp["X-Request-ID"]) == 32


def _can_create_roles() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user")
        return bool(cur.fetchone()[0])


def test_app_role_cannot_update_or_delete_audit_rows():
    """Applies scripts/sql/02_app_grants.sql to a throwaway role and proves the audit table is append-only."""
    if not _can_create_roles():
        pytest.skip("database user lacks CREATEROLE; run this test on a dev database where it has it")
    event = record("test.append_only")
    role = "etqa_app_test_role"
    sql = GRANTS_SQL.read_text(encoding="utf-8").replace("etqa_app", role)
    with connection.cursor() as cur:
        cur.execute(f"DROP ROLE IF EXISTS {role}")
        cur.execute(f"CREATE ROLE {role} NOLOGIN")
        cur.execute(f"GRANT {role} TO CURRENT_USER")  # PostgreSQL 16 requires membership to SET ROLE
        try:
            cur.execute(sql)
            cur.execute(f"SET ROLE {role}")
            cur.execute("SELECT count(*) FROM audit_auditevent")  # reading is allowed
            cur.execute("INSERT INTO audit_auditevent (created_at, actor_label, action, object_type, object_id, request_id, detail) "
                        "VALUES (now(), '', 'test.insert', '', '', '', '{}')")
            for stmt in (f"UPDATE audit_auditevent SET action = 'x' WHERE id = {event.id}",
                         f"DELETE FROM audit_auditevent WHERE id = {event.id}"):
                with pytest.raises(ProgrammingError, match="permission denied"):
                    with transaction.atomic():
                        cur.execute(stmt)
        finally:
            cur.execute("RESET ROLE")
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
            cur.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
            cur.execute(f"REVOKE ALL ON SCHEMA public FROM {role}")
            cur.execute(f"DROP ROLE {role}")
