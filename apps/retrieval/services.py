"""Hybrid retrieval (ADR-05): full-text + identifier trigram + vector, fused with Reciprocal Rank Fusion.
Every query takes an AccessScope and filters by collection inside SQL, before ranking (ADR-07)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramWordSimilarity
from django.db.models import F

from apps.access.scope import AccessScope
from apps.sysconfig.services import get as setting

from . import text as textutil
from . import vectors
from .models import Chunk, ChunkEmbedding, EmbeddingSpace

log = logging.getLogger("etqa.retrieval")


@dataclass
class Passage:
    chunk_id: int
    document_id: int
    document_title: str
    version_id: int
    version_no: int
    collection_id: int
    locator: str
    section_path: str
    text: str
    score: float
    signals: list[str]
    flags: list[str]


@dataclass
class RetrievalResult:
    passages: list[Passage]
    vector_used: bool
    notes: list[str] = field(default_factory=list)


def active_space() -> EmbeddingSpace | None:
    return EmbeddingSpace.objects.filter(is_active=True).first()


def ensure_space(model_key: str, runtime_name: str, dims: int) -> EmbeddingSpace:
    space, _ = EmbeddingSpace.objects.get_or_create(model_key=model_key, runtime_name=runtime_name, dims=dims)
    if not EmbeddingSpace.objects.filter(is_active=True).exists():
        EmbeddingSpace.objects.filter(pk=space.pk).update(is_active=True)
        space.is_active = True
    return space


def _scoped(scope: AccessScope, collection_ids: list[int] | None) -> list[int]:
    allowed = set(scope.readable)
    if collection_ids:
        allowed &= set(collection_ids)
    return sorted(allowed)


def _fts(terms: list[str], ids: list[int], k: int, document_id: int | None) -> list[int]:
    if not terms:
        return []
    query = SearchQuery(" | ".join(terms), config="simple", search_type="raw")
    qs = Chunk.objects.filter(collection_id__in=ids, tsv=query)
    if document_id:
        qs = qs.filter(document_id=document_id)
    return list(qs.annotate(rank=SearchRank(F("tsv"), query, cover_density=True)).order_by("-rank", "id")
                .values_list("id", flat=True)[:k])


def _trigram(idents: list[str], ids: list[int], k: int, document_id: int | None) -> list[int]:
    hits: dict[int, float] = {}
    threshold = setting("retrieval.trigram_threshold")
    for ident in idents[:5]:
        qs = Chunk.objects.filter(collection_id__in=ids).annotate(
            sim=TrigramWordSimilarity(ident.lower(), "identifiers")).filter(sim__gte=threshold)
        if document_id:
            qs = qs.filter(document_id=document_id)
        for cid, sim in qs.order_by("-sim").values_list("id", "sim")[:k]:
            hits[cid] = max(hits.get(cid, 0), sim)
    return [cid for cid, _ in sorted(hits.items(), key=lambda kv: -kv[1])][:k]


def _rrf(lists: dict[str, list[int]], k_const: int) -> dict[int, tuple[float, list[str]]]:
    fused: dict[int, tuple[float, list[str]]] = {}
    for signal, ids in lists.items():
        for rank, cid in enumerate(ids, 1):
            score, signals = fused.get(cid, (0.0, []))
            fused[cid] = (score + 1.0 / (k_const + rank), signals + [signal])
    return fused


def search(query: str, scope: AccessScope, *, collection_ids: list[int] | None = None, document_id: int | None = None,
           k: int | None = None, query_vector: list[float] | None = None) -> RetrievalResult:
    ids = _scoped(scope, collection_ids)
    if not ids:
        return RetrievalResult([], False, ["no readable collections in scope"])
    terms = textutil.query_terms(query)
    idents = textutil.identifiers(query)
    lists = {"fts": _fts(terms, ids, setting("retrieval.k_fts"), document_id),
             "identifier": _trigram(idents, ids, setting("retrieval.k_trigram"), document_id)}
    notes, vector_used = [], False
    space = active_space()
    if space is not None:
        try:
            if query_vector is None:
                from apps.ai.services import AIFailed, AIUnavailable, embed  # ai is a lower layer
                try:
                    query_vector = embed([textutil.normalize(query)])[0][0]
                except (AIUnavailable, AIFailed) as exc:
                    notes.append(f"semantic search skipped: {exc}")
            if query_vector is not None:
                hits = vectors.search(query_vector, space, ids, setting("retrieval.k_vector"), document_id)
                floor = setting("retrieval.min_vector_similarity")
                keyword = set(lists["fts"]) | set(lists["identifier"])
                lists["vector"] = [cid for cid, sim in hits if sim >= floor or cid in keyword]
                vector_used = True
        except vectors.ScopeTooLarge as exc:
            notes.append(str(exc))
    fused = _rrf(lists, setting("retrieval.rrf_k"))
    top = sorted(fused.items(), key=lambda kv: -kv[1][0])[: k or setting("retrieval.final_k")]
    chunks = {c.id: c for c in Chunk.objects.filter(id__in=[cid for cid, _ in top], collection_id__in=ids)
              .select_related("document", "version")}
    passages = [Passage(chunk_id=c.id, document_id=c.document_id, document_title=c.document.title,
                        version_id=c.version_id, version_no=c.version.version_no, collection_id=c.collection_id,
                        locator=c.locator, section_path=c.section_path, text=c.text, score=round(score, 5),
                        signals=signals, flags=c.flags)
                for cid, (score, signals) in top if (c := chunks.get(cid)) is not None]
    return RetrievalResult(passages, vector_used, notes)


def replace_chunks(version, chunks: list[dict]) -> int:
    """Atomically swaps a version's chunks (caller holds the transaction). Reruns never duplicate passages."""
    Chunk.objects.filter(version=version).delete()
    objs = [Chunk(version=version, document_id=version.document_id, collection_id=version.document.collection_id,
                  ordinal=i, **c) for i, c in enumerate(chunks)]
    Chunk.objects.bulk_create(objs, batch_size=500)
    Chunk.objects.filter(version=version).update(tsv=SearchVector("search_text", config="simple"))
    return len(objs)


def chunks_missing_embeddings(version_id: int, space: EmbeddingSpace):
    return Chunk.objects.filter(version_id=version_id).exclude(embeddings__space=space).order_by("ordinal")


def store_embeddings(space: EmbeddingSpace, pairs: list[tuple[int, list[float]]]) -> None:
    ChunkEmbedding.objects.bulk_create([ChunkEmbedding(chunk_id=cid, space=space, vector=vec) for cid, vec in pairs],
                                       ignore_conflicts=True)
