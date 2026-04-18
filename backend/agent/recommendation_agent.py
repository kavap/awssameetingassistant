"""Recommendation Agent.

Consumes CCMUpdateEvents from a bounded queue, searches the KB,
reranks with Haiku, synthesizes with Sonnet, broadcasts to WebSocket.

All boto3 calls run in executor to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from functools import partial

import boto3

from backend.ccm.models import CCMUpdateEvent
from backend.config import settings
from backend.knowledge_base import embeddings, qdrant_client

logger = logging.getLogger(__name__)

_bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)

# Cooldown: don't re-trigger for the same primary topic within N seconds
COOLDOWN_SECONDS = 20


def _invoke_bedrock_sync(model_id: str, prompt_messages: list[dict], max_tokens: int = 1024) -> str:
    """Synchronous Bedrock invoke — always run via executor."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": prompt_messages,
    })
    response = _bedrock.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


async def _invoke_bedrock(model_id: str, messages: list[dict], max_tokens: int = 1024) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, partial(_invoke_bedrock_sync, model_id, messages, max_tokens)
    )


def _build_search_query(event: CCMUpdateEvent) -> str:
    """Build a natural language search query from the CCM context."""
    ctx = event.context_snapshot
    parts = []

    # Add top active topic
    topics = ctx.get("active_topics", [])
    if topics:
        top = topics[0]
        parts.append(top["name"].replace("_", " "))

    # Add mentioned AWS services
    services = [
        name for name, svc in ctx.get("mentioned_services", {}).items()
        if svc["category"] == "aws"
    ]
    if services:
        parts.append(" ".join(services[:3]))

    # Add competitor services for comparison queries
    competitors = [
        name for name, svc in ctx.get("mentioned_services", {}).items()
        if svc["category"] == "competitor"
    ]
    if competitors:
        parts.append("vs " + " ".join(competitors[:2]))

    # Add trigger text excerpt
    parts.append(event.trigger_text[:100])

    return " ".join(parts)[:300]


async def _rerank_chunks(chunks: list[dict], context: str, query: str) -> list[dict]:
    """Use Haiku to select the top 3 most relevant chunks."""
    if len(chunks) <= 3:
        return chunks

    chunks_text = "\n\n".join(
        f"[{i}] {c['title'] or c['url']}\n{c['text'][:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = f"""You are helping an AWS Solutions Architect in a live meeting.

Meeting context: {context[:400]}
Query: {query}

Given these {len(chunks)} document chunks, return ONLY a JSON array of the 3 most relevant chunk indices (0-based), most relevant first. Example: [2, 0, 4]

Chunks:
{chunks_text}

Return only the JSON array, nothing else."""

    try:
        response = await _invoke_bedrock(
            settings.bedrock_haiku_model,
            [{"role": "user", "content": prompt}],
            max_tokens=50,
        )
        indices = json.loads(response.strip())
        return [chunks[i] for i in indices if 0 <= i < len(chunks)]
    except Exception as e:
        logger.warning(f"Rerank failed: {e}. Using top 3 by score.")
        return chunks[:3]


async def _synthesize_recommendation(
    chunks: list[dict],
    context: str,
    trigger_text: str,
) -> dict:
    """Use Sonnet to synthesize a recommendation card from retrieved chunks."""
    chunks_context = "\n\n".join(
        f"Source: {c['url']}\nTitle: {c['title']}\n{c['text'][:500]}"
        for c in chunks
    )

    prompt = f"""You are a real-time AI assistant helping an AWS Solutions Architect during a live customer meeting.

Current meeting context:
{context[:600]}

What was just discussed: {trigger_text[:200]}

Relevant AWS documentation and knowledge:
{chunks_context}

Based on this information, generate a proactive recommendation card for the SA. Return ONLY valid JSON in this exact format:
{{
  "title": "brief title (max 10 words)",
  "summary": "1-2 sentence answer or recommendation directly addressing the meeting context",
  "service_mentioned": ["list", "of", "aws", "services"],
  "action_items": ["specific action or talking point 1", "action 2", "action 3"],
  "source_urls": ["url1", "url2"],
  "confidence": 0.85
}}

Be specific, actionable, and relevant to what is being discussed right now. Do not include markdown formatting."""

    try:
        response = await _invoke_bedrock(
            settings.bedrock_sonnet_model,
            [{"role": "user", "content": prompt}],
            max_tokens=600,
        )
        card = json.loads(response.strip())
        card["id"] = str(uuid.uuid4())
        card["trigger"] = trigger_text[:100]
        return card
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return {
            "id": str(uuid.uuid4()),
            "title": "AWS Recommendation",
            "summary": f"Related to: {trigger_text[:100]}",
            "service_mentioned": [],
            "action_items": [],
            "source_urls": [c["url"] for c in chunks[:2]],
            "confidence": 0.3,
            "trigger": trigger_text[:100],
        }


class RecommendationAgent:
    """Consumes CCMUpdateEvents and emits recommendation cards over WebSocket."""

    def __init__(self, ws_manager, event_queue: asyncio.Queue) -> None:
        self._ws = ws_manager
        self._queue = event_queue
        self._last_trigger: dict[str, float] = {}  # topic -> last trigger time
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self.run(), name="recommendation-agent")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def run(self) -> None:
        logger.info("RecommendationAgent started.")
        while self._running:
            try:
                event: CCMUpdateEvent = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            await self._process_event(event)

    async def _process_event(self, event: CCMUpdateEvent) -> None:
        ctx = event.context_snapshot
        topics = ctx.get("active_topics", [])
        topic_key = topics[0]["name"] if topics else "general"

        # Cooldown check
        last = self._last_trigger.get(topic_key, 0)
        if time.time() - last < COOLDOWN_SECONDS:
            logger.debug(f"Cooldown active for topic: {topic_key}")
            return

        self._last_trigger[topic_key] = time.time()

        try:
            query = _build_search_query(event)
            logger.info(f"KB search: {query[:80]}")

            # Embed query
            dense_vec = await embeddings.embed(query)
            sparse_vec = qdrant_client.compute_sparse_vector(query)

            # Hybrid search
            chunks = await qdrant_client.hybrid_search(
                dense_vec=dense_vec,
                sparse_vec=sparse_vec,
                limit=8,
            )

            if not chunks:
                logger.info("No KB results found.")
                return

            # Rerank with Haiku
            context_str = (
                f"Topics: {', '.join(t['name'] for t in topics[:3])}\n"
                f"Services: {', '.join(ctx.get('mentioned_services', {}).keys())}"
            )
            top_chunks = await _rerank_chunks(chunks, context_str, query)

            # Synthesize with Sonnet
            card = await _synthesize_recommendation(
                top_chunks, context_str, event.trigger_text
            )

            # Broadcast
            await self._ws.broadcast({
                "type": "recommendation",
                "ts": time.time(),
                "payload": card,
            })
            logger.info(f"Recommendation emitted: {card.get('title', '')}")

        except Exception as e:
            logger.error(f"RecommendationAgent error: {e}", exc_info=True)
