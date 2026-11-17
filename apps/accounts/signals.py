"""Audit hooks for authentication and group membership changes."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.audit.services import record

from .middleware import SESSION_STARTED_KEY
from .models import User


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    import time

    if request is not None and hasattr(request, "session"):
        request.session[SESSION_STARTED_KEY] = time.time()
    record("auth.login", actor=user, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record("auth.logout", actor=user, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # credentials has the password already masked by Django; we record only the username.
    record("auth.login_failed", request=request, username=str(credentials.get("username", ""))[:150])


@receiver(m2m_changed, sender=User.groups.through)
def on_groups_changed(sender, instance, action, pk_set, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and isinstance(instance, User):
        record("access.user_groups_changed", obj=instance, change=action.removeprefix("post_"),
               group_ids=sorted(pk_set or []))
