"""Content-addressed file store outside the web root (ADR-11)."""
import hashlib
import os
import pathlib
import tempfile

from django.conf import settings


def root() -> pathlib.Path:
    path = pathlib.Path(settings.ETQA_FILE_ROOT)
    path.mkdir(parents=True, exist_ok=True)
    return path


def store(uploaded) -> tuple[str, str, int]:
    """Streams an upload to a temp file while hashing, then moves it to ab/cd/<sha256>.
    The file is flushed to disk before the caller commits its database row (backup ordering, section 3)."""
    digest = hashlib.sha256()
    size = 0
    tmp_dir = root() / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=tmp_dir)
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in uploaded.chunks():
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        sha = digest.hexdigest()
        rel = f"{sha[:2]}/{sha[2:4]}/{sha}"
        final = root() / rel
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            os.remove(tmp_name)
        else:
            os.replace(tmp_name, final)
        return sha, rel, size
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def path_of(rel: str) -> pathlib.Path:
    full = (root() / rel).resolve()
    if root().resolve() not in full.parents:
        raise ValueError("path escapes the file root")
    return full
