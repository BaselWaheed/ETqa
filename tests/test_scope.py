"""AccessScope decides what text can ever reach a prompt (ADR-07)."""
from apps.access.roles import ADMIN, QA_ENGINEER, REVIEWER, VIEWER
from apps.access.scope import AccessScope, build_scope, can_upload
from apps.access.models import CollectionGrant


def test_scope_contains_only_granted_active_collections(users, collections):
    scope = build_scope(users[QA_ENGINEER])
    assert scope.readable == {collections["billing"].id}  # archived is inactive, hr not granted
    assert not scope.can_read(collections["hr"].id)


def test_reviewer_sees_only_hr(users, collections):
    assert build_scope(users[REVIEWER]).readable == {collections["hr"].id}


def test_admin_reads_and_manages_all_active(users, collections):
    scope = build_scope(users[ADMIN])
    assert scope.readable == {collections["billing"].id, collections["hr"].id}
    assert scope.manageable == scope.readable


def test_inactive_and_anonymous_users_get_empty_scope(users, collections):
    from django.contrib.auth.models import AnonymousUser

    viewer = users[VIEWER]
    viewer.is_active = False
    viewer.save()
    assert build_scope(viewer) == AccessScope(user_id=None, readable=frozenset(), manageable=frozenset())
    assert build_scope(AnonymousUser()).readable == frozenset()


def test_removing_group_removes_access_immediately(users, collections, roles):
    viewer = users[VIEWER]
    assert build_scope(viewer).can_read(collections["billing"].id)
    viewer.groups.remove(roles[VIEWER])
    assert not build_scope(viewer).can_read(collections["billing"].id)


def test_upload_rule(users, collections, roles):
    qa, reviewer, viewer = users[QA_ENGINEER], users[REVIEWER], users[VIEWER]
    billing, hr = collections["billing"], collections["hr"]
    # QA Engineer: read grant only -> no upload; manage grant -> upload
    assert not can_upload(qa, build_scope(qa), billing.id)
    CollectionGrant.objects.filter(collection=billing, group=roles[QA_ENGINEER]).update(level="manage")
    assert can_upload(qa, build_scope(qa), billing.id)
    # Reviewer: role allows upload, but only into collections they can read
    assert can_upload(reviewer, build_scope(reviewer), hr.id)
    assert not can_upload(reviewer, build_scope(reviewer), billing.id)
    # Viewer never, even with a read grant
    assert not can_upload(viewer, build_scope(viewer), billing.id)
