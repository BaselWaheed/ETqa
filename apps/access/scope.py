"""AccessScope: the set of collections a user may read, computed once per request or job (ADR-07).

Every retrieval query in later phases takes an AccessScope and filters with
`collection_id = ANY(:readable)` inside the ranking query, never afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Collection, CollectionGrant


@dataclass(frozen=True)
class AccessScope:
    user_id: int | None
    readable: frozenset[int]
    manageable: frozenset[int]

    def can_read(self, collection_id: int) -> bool:
        return collection_id in self.readable

    def can_manage(self, collection_id: int) -> bool:
        return collection_id in self.manageable

    @classmethod
    def empty(cls) -> "AccessScope":
        return cls(user_id=None, readable=frozenset(), manageable=frozenset())


def build_scope(user) -> AccessScope:
    if user is None or not user.is_authenticated or not user.is_active:
        return AccessScope.empty()
    active = Collection.objects.filter(is_active=True)
    if user.has_perm("access.manage_collections"):
        ids = frozenset(active.values_list("id", flat=True))
        return AccessScope(user_id=user.pk, readable=ids, manageable=ids)
    grants = CollectionGrant.objects.filter(group__user=user, collection__is_active=True).values_list("collection_id", "level")
    readable: set[int] = set()
    manageable: set[int] = set()
    for collection_id, level in grants:
        readable.add(collection_id)
        if level == CollectionGrant.Level.MANAGE:
            manageable.add(collection_id)
    return AccessScope(user_id=user.pk, readable=frozenset(readable), manageable=frozenset(manageable))


def can_upload(user, scope: AccessScope, collection_id: int) -> bool:
    """Upload rule from the permission matrix: role capability on a readable collection, or a manage grant."""
    if scope.can_manage(collection_id):
        return True
    return scope.can_read(collection_id) and user.has_perm("access.upload_documents")
