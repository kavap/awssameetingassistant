"""Integration tests for the Qdrant KB client. Requires Docker + Qdrant running."""
import uuid

import pytest

from backend.knowledge_base.qdrant_client import (
    compute_sparse_vector,
    drop_collection,
    ensure_collection,
    hybrid_search,
    upsert_document,
)


@pytest.fixture(autouse=True)
async def fresh_collection():
    """Ensure a clean collection for each test."""
    await drop_collection()
    await ensure_collection()
    yield
    await drop_collection()


async def test_ensure_collection_idempotent():
    """Calling ensure_collection twice should not raise."""
    await ensure_collection()
    await ensure_collection()  # should be no-op


async def test_upsert_and_search():
    """Inserting a doc and searching with the same vector should return it."""
    text = "Amazon Redshift is a fully managed petabyte-scale data warehouse."
    dense_vec = [0.1] * 1024  # fake dense vector
    sparse_vec = compute_sparse_vector(text)

    doc_id = str(uuid.uuid4())
    await upsert_document(
        doc_id=doc_id,
        text=text,
        metadata={"url": "https://example.com", "title": "Redshift Overview"},
        dense_vec=dense_vec,
        sparse_vec=sparse_vec,
    )

    results = await hybrid_search(
        dense_vec=dense_vec,
        sparse_vec=sparse_vec,
        limit=5,
    )
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert doc_id in ids


async def test_compute_sparse_vector():
    vec = compute_sparse_vector("Amazon S3 is object storage")
    assert len(vec.indices) > 0
    assert len(vec.indices) == len(vec.values)
    assert all(v > 0 for v in vec.values)
