"""Handlers are plain functions registered by business modules in AppConfig.ready(); jobs never imports them."""
from dataclasses import dataclass
from typing import Callable


class RetryableError(Exception):
    """Transient failure (model timeout, connection refused): retry with backoff."""


class PermanentError(Exception):
    """Bad input or missing data: retrying cannot help; the job goes to 'dead'."""


class DeferJob(Exception):
    """Not now (e.g. vision window while chats wait): reschedule without using an attempt."""

    def __init__(self, seconds: float, reason: str = ""):
        super().__init__(reason)
        self.seconds = seconds


class Unavailable(Exception):
    """A dependency the queue needs (Ollama) is down: the worker stops claiming this queue for a while."""


@dataclass(frozen=True)
class HandlerSpec:
    kind: str
    func: Callable
    queue: str
    priority: int
    max_attempts: int | None


_HANDLERS: dict[str, HandlerSpec] = {}
_QUEUE_GATES: dict[str, Callable[[], bool]] = {}


def register(kind: str, *, queue: str = "general", priority: int = 10, max_attempts: int | None = None):
    def decorator(func):
        _HANDLERS[kind] = HandlerSpec(kind, func, queue, priority, max_attempts)
        return func
    return decorator


def register_queue_gate(queue: str, check: Callable[[], bool]) -> None:
    """A function returning False stops workers on that queue from claiming (e.g. Ollama down)."""
    _QUEUE_GATES[queue] = check


def spec(kind: str) -> HandlerSpec | None:
    return _HANDLERS.get(kind)


def gate_open(queue: str) -> bool:
    check = _QUEUE_GATES.get(queue)
    try:
        return check() if check else True
    except Exception:  # noqa: BLE001 - a broken gate must not stop the worker loop
        return False
