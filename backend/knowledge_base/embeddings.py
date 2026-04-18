"""Bedrock Titan Embeddings v2 wrapper.

Synchronous boto3 call wrapped in executor to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import json
from functools import partial

import boto3

from backend.config import settings

_bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)


def _embed_sync(text: str) -> list[float]:
    """Synchronous embedding call — run via executor."""
    body = json.dumps({"inputText": text[:8000]})  # Titan v2 max 8192 tokens
    response = _bedrock_client.invoke_model(
        modelId=settings.bedrock_embedding_model,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


async def embed(text: str) -> list[float]:
    """Async embedding — runs the synchronous boto3 call in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_embed_sync, text))


def embed_sync(text: str) -> list[float]:
    """Synchronous version for use in ingestion scripts."""
    return _embed_sync(text)
