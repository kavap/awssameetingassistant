"""Amazon Bedrock Knowledge Base retrieval client.

Uses bedrock-agent-runtime to query a pre-configured Bedrock KB.
The KB handles embedding (Cohere embed v3) and vector search internally —
no manual embedding needed at query time.

Supports HYBRID search (semantic + keyword) which performs best for
AWS documentation and technical content.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial

import boto3

from backend.config import settings

logger = logging.getLogger(__name__)

_agent_runtime = boto3.client(
    "bedrock-agent-runtime", region_name=settings.aws_region
)


def _retrieve_sync(query: str, limit: int) -> list[dict]:
    """Synchronous KB retrieve — always run via executor."""
    if not settings.bedrock_kb_id:
        logger.warning("BEDROCK_KB_ID not set — skipping KB retrieval.")
        return []

    params: dict = {
        "knowledgeBaseId": settings.bedrock_kb_id,
        "retrievalQuery": {"text": query},
        "retrievalConfiguration": {
            "vectorSearchConfiguration": {
                "numberOfResults": limit,
            }
        },
    }

    # Enable hybrid search if configured (semantic + keyword fusion)
    search_type = settings.bedrock_kb_search_type.upper()
    if search_type in ("HYBRID", "SEMANTIC", "KEYWORD"):
        params["retrievalConfiguration"]["vectorSearchConfiguration"][
            "overrideSearchType"
        ] = search_type

    response = _agent_runtime.retrieve(**params)

    results = []
    for item in response.get("retrievalResults", []):
        content = item.get("content", {})
        metadata = item.get("metadata", {})
        location = item.get("location", {})

        # Extract source URL from metadata (set during ingestion) or S3 URI
        source_url = (
            metadata.get("source_url")
            or metadata.get("x-amz-bedrock-kb-source-uri", "")
            or location.get("s3Location", {}).get("uri", "")
        )
        title = metadata.get("title", source_url)

        results.append({
            "text": content.get("text", ""),
            "score": item.get("score", 0.0),
            "url": source_url,
            "title": title,
            "chunk_index": metadata.get("chunk_index", 0),
        })

    return results


async def retrieve(query: str, limit: int | None = None) -> list[dict]:
    """Async retrieval from Bedrock KB using hybrid search."""
    n = limit or settings.bedrock_kb_num_results
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, partial(_retrieve_sync, query, n))
    except Exception as e:
        logger.error(f"Bedrock KB retrieve failed: {e}")
        return []


def is_configured() -> bool:
    """Return True if the KB is configured (KB ID is set)."""
    return bool(settings.bedrock_kb_id)
