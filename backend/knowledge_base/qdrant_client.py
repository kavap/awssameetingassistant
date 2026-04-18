"""Qdrant async client wrapper with hybrid search (dense KNN + sparse BM25)."""
from __future__ import annotations

import re
from collections import Counter

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from backend.config import settings

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    return _client


async def ensure_collection() -> None:
    """Create the KB collection if it doesn't exist. Idempotent."""
    client = get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if settings.qdrant_collection in names:
        return

    await client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={"dense": VectorParams(size=settings.vector_size, distance=Distance.COSINE)},
        sparse_vectors_config={
            "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
        },
        on_disk_payload=True,
    )


async def drop_collection() -> None:
    client = get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if settings.qdrant_collection in names:
        await client.delete_collection(settings.qdrant_collection)


def compute_sparse_vector(text: str) -> SparseVector:
    """Compute a term-frequency sparse vector from text."""
    tokens = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
    counts = Counter(tokens)
    # Use a stable integer index per unique token (hash-based, 2^20 buckets)
    indices = [hash(token) % (2**20) for token in counts]
    values = [float(v) for v in counts.values()]
    return SparseVector(indices=indices, values=values)


async def upsert_document(
    doc_id: str,
    text: str,
    metadata: dict,
    dense_vec: list[float],
    sparse_vec: SparseVector,
) -> None:
    client = get_client()
    point = PointStruct(
        id=doc_id,
        vector={"dense": dense_vec, "sparse": sparse_vec},
        payload={**metadata, "text": text},
    )
    await client.upsert(
        collection_name=settings.qdrant_collection,
        points=[point],
    )


async def hybrid_search(
    dense_vec: list[float],
    sparse_vec: SparseVector,
    limit: int = 8,
    aws_services_filter: list[str] | None = None,
) -> list[dict]:
    """Hybrid search using RRF fusion of dense KNN + sparse BM25."""
    client = get_client()

    query_filter = None
    if aws_services_filter:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="aws_services",
                    match=MatchAny(any=aws_services_filter),
                )
            ]
        )

    results = await client.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=limit * 2),
            Prefetch(query=sparse_vec, using="sparse", limit=limit * 2),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "id": str(point.id),
            "score": point.score,
            "text": point.payload.get("text", ""),
            "url": point.payload.get("url", ""),
            "title": point.payload.get("title", ""),
            "chunk_index": point.payload.get("chunk_index", 0),
        }
        for point in results.points
    ]
