"""The permission matrix from the architecture doc (section 6), checked role by role."""
import pytest
from django.contrib.auth.models import Group

from apps.access.models import CAPABILITIES
from apps.access.roles import ADMIN, QA_ENGINEER, REVIEWER, VIEWER
from apps.access.services import bootstrap_roles

Y, N = True, False
# capability: (Admin, Reviewer, QA Engineer, Viewer)
MATRIX = {
    "use_chat": (Y, Y, Y, Y),
    "save_chat_history": (Y, Y, Y, N),
    "search_documents": (Y, Y, Y, Y),
    "upload_documents": (Y, Y, N, N),  # QA Engineers upload through a collection "manage" grant
    "delete_documents": (Y, N, N, N),
    "generate_test_cases": (Y, Y, Y, N),
    "export_excel": (Y, Y, Y, N),
    "give_feedback": (Y, Y, Y, N),
    "review_knowledge": (Y, Y, N, N),
    "manage_users": (Y, N, N, N),
    "manage_collections": (Y, N, N, N),
    "configure_models": (Y, N, N, N),
    "view_audit": (Y, N, N, N),
    "manage_any_job": (Y, N, N, N),
}
ROLE_ORDER = (ADMIN, REVIEWER, QA_ENGINEER, VIEWER)


def test_matrix_covers_every_capability():
    assert set(MATRIX) == {code for code, _ in CAPABILITIES}


@pytest.mark.parametrize("capability", sorted(MATRIX))
@pytest.mark.parametrize("role_index", range(4))
def test_role_capability(users, capability, role_index):
    role = ROLE_ORDER[role_index]
    assert users[role].has_perm(f"access.{capability}") is MATRIX[capability][role_index]


def test_bootstrap_is_idempotent_and_keeps_admin_additions(roles):
    viewer = Group.objects.get(name=VIEWER)
    count = viewer.permissions.count()
    added = bootstrap_roles()
    assert all(n == 0 for n in added.values())
    assert viewer.permissions.count() == count


def test_user_without_role_has_no_capabilities(make_user):
    nobody = make_user("nobody")
    assert not any(nobody.has_perm(f"access.{c}") for c in MATRIX)
