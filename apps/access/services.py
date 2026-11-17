"""Public interface of the access module."""
from django.contrib.auth.models import Group, Permission
from django.db import transaction

from apps.audit.services import record

from .models import Collection, CollectionGrant
from .roles import ADMIN, ADMIN_MODEL_PERMISSIONS, ROLE_CAPABILITIES
from .scope import AccessScope, build_scope, can_upload  # noqa: F401  (re-exported)


@transaction.atomic
def bootstrap_roles() -> dict[str, int]:
    """Create the four roles with their default capabilities. Idempotent; adds missing defaults only,
    so permissions an admin added later are kept."""
    added: dict[str, int] = {}
    for role, codenames in ROLE_CAPABILITIES.items():
        group, _ = Group.objects.get_or_create(name=role)
        perms = list(Permission.objects.filter(content_type__app_label="access", codename__in=codenames))
        missing = set(codenames) - {p.codename for p in perms}
        if missing:
            raise RuntimeError(f"Capabilities not found (run migrate first): {sorted(missing)}")
        if role == ADMIN:
            for app_label, model, actions in ADMIN_MODEL_PERMISSIONS:
                perms += list(Permission.objects.filter(
                    content_type__app_label=app_label, content_type__model=model,
                    codename__in=[f"{a}_{model}" for a in actions]))
        before = group.permissions.count()
        group.permissions.add(*perms)
        added[role] = group.permissions.count() - before
    return added


@transaction.atomic
def create_collection(*, actor, request=None, name: str, slug: str, business_unit: str = "", description: str = "") -> Collection:
    collection = Collection.objects.create(name=name, slug=slug, business_unit=business_unit, description=description)
    record("access.collection_created", actor=actor, obj=collection, request=request, slug=slug)
    return collection


@transaction.atomic
def set_grant(*, actor, request=None, collection: Collection, group: Group, level: str) -> CollectionGrant:
    grant, created = CollectionGrant.objects.update_or_create(collection=collection, group=group, defaults={"level": level})
    record("access.grant_set", actor=actor, obj=collection, request=request,
           group=group.name, level=level, created=created)
    return grant


@transaction.atomic
def remove_grant(*, actor, request=None, collection: Collection, group: Group) -> bool:
    deleted, _ = CollectionGrant.objects.filter(collection=collection, group=group).delete()
    if deleted:
        record("access.grant_removed", actor=actor, obj=collection, request=request, group=group.name)
    return bool(deleted)


def scope_for(user) -> AccessScope:
    return build_scope(user)
