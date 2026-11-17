"""Per-request correlation ID, available to logging and audit without passing the request around."""
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("etqa_request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()
