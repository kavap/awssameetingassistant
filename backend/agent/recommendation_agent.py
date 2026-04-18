"""Recommendation Agent.

Consumes CCMUpdateEvents from a bounded queue, queries Bedrock Knowledge Base,
reranks with Claude Haiku, synthesizes a card with Claude Sonnet, broadcasts to WebSocket.

Bedrock KB handles embedding (Cohere v3) and hybrid search internally —
no manual embedding needed at query time.
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
from backend.knowledge_base import bedrock_kb

logger = logging.getLogger(__name__)

_bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)

COOLDOWN_SECONDS = 20


def _invoke_bedrock_sync(model_id: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Synchronous Bedrock Claude invoke — always run via executor."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
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
    """Build a focused natural language query from CCM state for KB retrieval."""
    ctx = event.context_snapshot
    parts = []

    topics = ctx.get("active_topics", [])
    if topics:
        parts.append(topics[0]["name"].replace("_", " "))

    aws_svcs = [
        name for name, svc in ctx.get("mentioned_services", {}).items()
        if svc["category"] == "aws"
    ]
    if aws_svcs:
        parts.append(" ".join(aws_svcs[:3]))

    competitors = [
        name for name, svc in ctx.get("mentioned_services", {}).items()
        if svc["category"] == "competitor"
    ]
    if competitors:
        parts.append("vs " + " ".join(competitors[:2]))

    parts.append(event.trigger_text[:100])

    return " ".join(parts)[:300]


async def _rerank_chunks(chunks: list[dict], context: str, query: str) -> list[dict]:
    """Use Claude Haiku to pick the top 3 most relevant chunks."""
    if len(chunks) <= 3:
        return chunks

    chunks_text = "\n\n".join(
        f"[{i}] {c.get('title') or c.get('url', '')}\n{c['text'][:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        f"You are helping an AWS Solutions Architect in a live meeting.\n\n"
        f"Meeting context: {context[:400]}\n"
        f"Query: {query}\n\n"
        f"Given these {len(chunks)} document chunks, return ONLY a JSON array of the 3 "
        f"most relevant chunk indices (0-based), most relevant first. Example: [2, 0, 4]\n\n"
        f"Chunks:\n{chunks_text}\n\n"
        f"Return only the JSON array, nothing else."
    )
    try:
        response = await _invoke_bedrock(
            settings.bedrock_haiku_model,
            [{"role": "user", "content": prompt}],
            max_tokens=50,
        )
        indices = json.loads(response.strip())
        return [chunks[i] for i in indices if 0 <= i < len(chunks)]
    except Exception as e:
        logger.warning(f"Rerank failed ({e}), using top 3 by score.")
        return chunks[:3]


async def _synthesize_recommendation(
    chunks: list[dict],
    context: str,
    trigger_text: str,
) -> dict:
    """Use Claude Sonnet to synthesize a structured recommendation card."""
    grounding = "\n\n".join(
        f"Source: {c.get('url', '')}\nTitle: {c.get('title', '')}\n{c['text'][:500]}"
        for c in chunks
    )
    prompt = (
        "You are a real-time AI assistant helping an AWS Solutions Architect "
        "during a live customer meeting.\n\n"
        f"Current meeting context:\n{context[:600]}\n\n"
        f"What was just discussed: {trigger_text[:200]}\n\n"
        f"Relevant AWS knowledge:\n{grounding}\n\n"
        "Generate a proactive recommendation card. Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "brief title (max 10 words)",\n'
        '  "summary": "1-2 sentence answer directly addressing the meeting context",\n'
        '  "service_mentioned": ["list", "of", "aws", "services"],\n'
        '  "action_items": ["talking point 1", "point 2", "point 3"],\n'
        '  "source_urls": ["url1", "url2"],\n'
        '  "confidence": 0.85\n'
        "}\n\n"
        "Be specific, actionable, relevant to right now. No markdown formatting."
    )
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
            "source_urls": [c.get("url", "") for c in chunks[:2]],
            "confidence": 0.3,
            "trigger": trigger_text[:100],
        }


class RecommendationAgent:
    """Consumes CCMUpdateEvents → Bedrock KB → Haiku rerank → Sonnet card → WebSocket."""

    def __init__(self, ws_manager, event_queue: asyncio.Queue) -> None:
        self._ws = ws_manager
        self._queue = event_queue
        self._last_trigger: dict[str, float] = {}
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

        last = self._last_trigger.get(topic_key, 0)
        if time.time() - last < COOLDOWN_SECONDS:
            logger.debug(f"Cooldown active for topic: {topic_key}")
            return

        self._last_trigger[topic_key] = time.time()

        if not bedrock_kb.is_configured():
            logger.warning(
                "Bedrock KB not configured (BEDROCK_KB_ID not set). "
                "Skipping recommendation. Set BEDROCK_KB_ID in .env after KB setup."
            )
            return

        try:
            query = _build_search_query(event)
            logger.info(f"KB retrieve: {query[:80]}")

            # Retrieve from Bedrock KB — embedding handled by KB internally
            chunks = await bedrock_kb.retrieve(query)

            if not chunks:
                logger.info("No KB results returned.")
                return

            context_str = (
                f"Topics: {', '.join(t['name'] for t in topics[:3])}\n"
                f"Services: {', '.join(ctx.get('mentioned_services', {}).keys())}"
            )

            top_chunks = await _rerank_chunks(chunks, context_str, query)
            card = await _synthesize_recommendation(top_chunks, context_str, event.trigger_text)

            await self._ws.broadcast({
                "type": "recommendation",
                "ts": time.time(),
                "payload": card,
            })
            logger.info(f"Recommendation emitted: {card.get('title', '')}")

        except Exception as e:
            logger.error(f"RecommendationAgent error: {e}", exc_info=True)
