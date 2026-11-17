"""Typed access to runtime settings: database override, else the default in defaults.py.

Values are cached per process for a few seconds so an admin change takes effect quickly without a restart.
"""
import time

from django.core.exceptions import ValidationError

from .defaults import DEFAULTS
from .models import SystemSetting

_CACHE: dict[str, object] = {}
_LOADED_AT = 0.0
_TTL = 5.0


def _load() -> None:
    global _LOADED_AT
    _CACHE.clear()
    _CACHE.update(dict(SystemSetting.objects.values_list("key", "value")))
    _LOADED_AT = time.monotonic()


def invalidate() -> None:
    global _LOADED_AT
    _LOADED_AT = 0.0


def get(key: str):
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key!r}; add it to apps/sysconfig/defaults.py")
    if time.monotonic() - _LOADED_AT > _TTL:
        _load()
    return _CACHE.get(key, DEFAULTS[key][0])


def validate(key: str, value) -> None:
    if key not in DEFAULTS:
        raise ValidationError(f"Unknown setting {key!r}.")
    default = DEFAULTS[key][0]
    numeric = (int, float)
    ok = (isinstance(value, numeric) and not isinstance(value, bool)) if isinstance(default, numeric) and not isinstance(default, bool) \
        else isinstance(value, type(default))
    if not ok:
        raise ValidationError(f"{key} must be of type {type(default).__name__}.")


def set_value(key: str, value, *, user=None) -> None:
    validate(key, value)
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value, "updated_by": user})
    invalidate()


def reset(key: str) -> None:
    SystemSetting.objects.filter(key=key).delete()
    invalidate()
