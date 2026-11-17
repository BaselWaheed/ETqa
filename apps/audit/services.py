"""Public interface of the audit module."""
from __future__ import annotations

from typing import Any

from .context import current_request_id
from .models import AuditEvent

FORBIDDEN_DETAIL_KEYS = {"password", "password1", "password2", "token", "secret", "prompt", "content", "text"}


def client_ip(request) -> str | None:
    # REMOTE_ADDR only: a TLS terminator in front of Waitress is local, so forwarded headers are not trusted here.
    return request.META.get("REMOTE_ADDR") if request is not None else None


def record(action: str, *, actor=None, obj=None, object_type: str = "", object_id: Any = "", request=None, **detail) -> AuditEvent:
    leaked = FORBIDDEN_DETAIL_KEYS.intersection(k.lower() for k in detail)
    if leaked:
        raise ValueError(f"Audit detail must not contain sensitive keys: {sorted(leaked)}")
    if obj is not None:
        object_type = object_type or obj._meta.label_lower
        object_id = object_id or obj.pk
    if actor is None and request is not None and getattr(request, "user", None) is not None and request.user.is_authenticated:
        actor = request.user
    return AuditEvent.objects.create(
        actor=actor if (actor is not None and getattr(actor, "pk", None)) else None,
        actor_label=getattr(actor, "username", "") or detail.pop("username", ""),
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id != "" else "",
        request_id=current_request_id(),
        ip=client_ip(request),
        detail=detail,
    )
