"""Login throttling per username and per client IP (section 6)."""
from django.conf import settings
from django.core.cache import cache


def _keys(username: str, ip: str | None) -> tuple[str, str]:
    return f"login-fail:user:{username.strip().lower()}", f"login-fail:ip:{ip or '-'}"


def is_locked(username: str, ip: str | None) -> bool:
    user_key, ip_key = _keys(username, ip)
    return (cache.get(user_key, 0) >= settings.LOGIN_MAX_FAILURES
            or cache.get(ip_key, 0) >= settings.LOGIN_MAX_FAILURES_PER_IP)


def register_failure(username: str, ip: str | None) -> None:
    timeout = settings.LOGIN_LOCK_MINUTES * 60
    for key in _keys(username, ip):
        cache.add(key, 0, timeout)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout)


def clear(username: str) -> None:
    cache.delete(_keys(username, None)[0])
