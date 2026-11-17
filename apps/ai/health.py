import time

from apps.sysconfig.services import get as setting

from . import client

_STATE = {"checked": 0.0, "ok": False, "models": []}


def ollama_available(force: bool = False) -> bool:
    if force or time.monotonic() - _STATE["checked"] > setting("ai.health_cache_seconds"):
        try:
            _STATE["models"] = client.tags()
            _STATE["ok"] = True
        except client.ModelError:
            _STATE["ok"], _STATE["models"] = False, []
        _STATE["checked"] = time.monotonic()
    return _STATE["ok"]


def pulled_models() -> list[str]:
    ollama_available()
    return list(_STATE["models"])


def reset_cache() -> None:
    _STATE["checked"] = 0.0
