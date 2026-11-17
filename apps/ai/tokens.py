"""Token counting (router step 3). Exact when a local tokenizer.json and the optional `tokenizers` package
exist for the model; otherwise a conservative character-based estimate (U12 fallback)."""
from functools import lru_cache

from apps.sysconfig.services import get as setting


@lru_cache(maxsize=8)
def _tokenizer(path: str):
    try:
        from tokenizers import Tokenizer
        return Tokenizer.from_file(path)
    except Exception:  # noqa: BLE001 - missing package or file -> estimate
        return None


def count(text: str, tokenizer_path: str = "") -> int:
    tok = _tokenizer(tokenizer_path) if tokenizer_path else None
    if tok is not None:
        return len(tok.encode(text).ids)
    return int(len(text) / setting("ai.char_per_token")) + 1


def is_exact(tokenizer_path: str) -> bool:
    return bool(tokenizer_path) and _tokenizer(tokenizer_path) is not None
