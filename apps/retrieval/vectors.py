"""Vector store interface with two backends (ADR-04): pgvector (indexed) and an array backend for
workstations where the extension cannot be installed. The access filter is inside both queries."""
from __future__ import annotations

import numpy as np
from django.db import DatabaseError, connection, transaction

from apps.sysconfig.services import get as setting

from .models import EmbeddingSpace


class ScopeTooLarge(Exception):
    pass


def pgvector_installed() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        return cur.fetchone() is not None


def backend_name() -> str:
    choice = setting("retrieval.vector_backend")
    if choice == "auto":
        return "pgvector" if pgvector_installed() else "array"
    return choice


def search(query_vec: list[float], space: EmbeddingSpace, collection_ids: list[int], k: int,
           document_id: int | None = None) -> list[tuple[int, float]]:
    if not collection_ids:
        return []
    if backend_name() == "pgvector":
        return _pgvector(query_vec, space, collection_ids, k, document_id)
    return _array(query_vec, space, collection_ids, k, document_id)


def _array(query_vec, space, collection_ids, k, document_id):
    extra, params = ("AND c.document_id = %s", [document_id]) if document_id else ("", [])
    with connection.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM retrieval_chunkembedding e JOIN retrieval_chunk c ON c.id = e.chunk_id "
                    f"WHERE e.space_id = %s AND c.collection_id = ANY(%s) {extra}", [space.id, collection_ids, *params])
        n = cur.fetchone()[0]
        if n > setting("retrieval.array_max_candidates"):
            raise ScopeTooLarge(f"{n} vectors in scope; install pgvector (ADR-04)")
        cur.execute(f"SELECT e.chunk_id, e.vector FROM retrieval_chunkembedding e JOIN retrieval_chunk c ON c.id = e.chunk_id "
                    f"WHERE e.space_id = %s AND c.collection_id = ANY(%s) {extra}", [space.id, collection_ids, *params])
        rows = cur.fetchall()
    if not rows:
        return []
    ids = np.array([r[0] for r in rows])
    mat = np.array([r[1] for r in rows], dtype=np.float32)
    q = np.asarray(query_vec, dtype=np.float32)
    sims = mat @ q / (np.linalg.norm(mat, axis=1) * (np.linalg.norm(q) or 1.0) + 1e-9)
    top = np.argsort(-sims)[:k]
    return [(int(ids[i]), float(sims[i])) for i in top]


def _pgvector(query_vec, space, collection_ids, k, document_id):
    dims = int(space.dims)
    extra, params = ("AND c.document_id = %s", [document_id]) if document_id else ("", [])
    literal = "[" + ",".join(f"{v:.7f}" for v in query_vec) + "]"
    with transaction.atomic(), connection.cursor() as cur:
        try:
            with transaction.atomic():  # savepoint: older pgvector rejects this setting
                cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")  # >= 0.8 keeps k results under filters
        except DatabaseError:
            pass
        cur.execute(
            f"SELECT e.chunk_id, 1 - ((e.vector::vector({dims})) <=> %s::vector) AS sim "
            f"FROM retrieval_chunkembedding e JOIN retrieval_chunk c ON c.id = e.chunk_id "
            f"WHERE e.space_id = %s AND c.collection_id = ANY(%s) {extra} "
            f"ORDER BY (e.vector::vector({dims})) <=> %s::vector LIMIT %s",
            [literal, space.id, collection_ids, *params, literal, k])
        return [(int(r[0]), float(r[1])) for r in cur.fetchall()]
