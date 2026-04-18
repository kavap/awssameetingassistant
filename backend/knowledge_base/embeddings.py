"""Cohere Embed v3 on Amazon Bedrock.

Cohere embed-english-v3 outputs 1024-dimensional vectors.
input_type must be "search_document" for KB ingestion
and "search_query" for runtime queries.

NOTE: When using Bedrock Knowledge Base for retrieval, you do NOT call
this module at query time — the KB handles embedding internally.
This module is used by scripts/ingest.py to embed documents before
uploading (optional pre-embedding) and can be used standalone.
"""
from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import Literal

import boto3

from backend.config import settings

_bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

InputType = Literal["search_document", "search_query", "classification", "clustering"]


def _embed_sync(text: str, input_type: InputType = "search_document") -> list[float]:
    """Synchronous Cohere embed call — run via executor for async use."""
    body = json.dumps({
        "texts": [text[:2048]],   # Cohere embed v3 max input length
        "input_type": input_type,
        "truncate": "END",
    })
    response = _bedrock_client.invoke_model(
        modelId=settings.bedrock_embedding_model,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    # Cohere response: {"embeddings": [[...]], "id": "...", ...}
    return result["embeddings"][0]


async def embed(text: str, input_type: InputType = "search_document") -> list[float]:
    """Async embed — wraps synchronous boto3 call in executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_embed_sync, text, input_type))


async def embed_query(text: str) -> list[float]:
    """Embed a search query (uses search_query input_type for better retrieval)."""
    return await embed(text, input_type="search_query")


def embed_sync(text: str, input_type: InputType = "search_document") -> list[float]:
    """Synchronous version — used in ingestion scripts."""
    return _embed_sync(text, input_type)
