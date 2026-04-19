"""AgentCore Runtime entrypoint — Recommendation Agent.

This file is deployed to Amazon Bedrock AgentCore Runtime.
It receives a CCM context snapshot + trigger query, runs
KB retrieve → Haiku rerank → Sonnet synthesis, and returns
a structured recommendation card.

Deploy:
    agentcore deploy --name recommendation-agent

Invoked by: backend/agentcore/client.py
"""
from __future__ import annotations

import json
import logging
import os
import uuid

import boto3
from bedrock_agentcore import BedrockAgentCoreApp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bedrock clients — read config from env vars injected by AgentCore Runtime
# ---------------------------------------------------------------------------

_region = os.environ.get("AWS_REGION", "us-east-1")
_bedrock = boto3.client("bedrock-runtime", region_name=_region)
_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=_region)

_HAIKU = os.environ.get("BEDROCK_HAIKU_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
_SONNET = os.environ.get("BEDROCK_SONNET_MODEL", "us.anthropic.claude-sonnet-4-6-20250514-v1:0")
_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
_KB_NUM_RESULTS = int(os.environ.get("BEDROCK_KB_NUM_RESULTS", "8"))
_KB_SEARCH_TYPE = os.environ.get("BEDROCK_KB_SEARCH_TYPE", "HYBRID")

# ---------------------------------------------------------------------------
# Knowledge Base retrieval
# ---------------------------------------------------------------------------

def _retrieve_kb(query: str) -> list[dict]:
    if not _KB_ID:
        logger.warning("BEDROCK_KB_ID not set — skipping KB retrieval.")
        return []
    try:
        resp = _agent_runtime.retrieve(
            knowledgeBaseId=_KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": _KB_NUM_RESULTS,
                    "overrideSearchType": _KB_SEARCH_TYPE,
                }
            },
        )
        results = []
        for r in resp.get("retrievalResults", []):
            meta = r.get("metadata", {})
            results.append({
                "text": r["content"]["text"],
                "score": float(r.get("score", 0.5)),
                "url": meta.get("source_url", ""),
                "title": meta.get("title", ""),
            })
        return results
    except Exception as e:
        logger.error(f"KB retrieve error: {e}")
        return []


# ---------------------------------------------------------------------------
# Haiku reranking
# ---------------------------------------------------------------------------

def _rerank(chunks: list[dict], context: str, query: str) -> list[dict]:
    if len(chunks) <= 3:
        return chunks
    chunks_text = "\n\n".join(
        f"[{i}] {c.get('title') or c.get('url', '')}\n{c['text'][:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        f"You are helping an AWS Solutions Architect in a live meeting.\n\n"
        f"Meeting context: {context[:400]}\nQuery: {query}\n\n"
        f"Return ONLY a JSON array of the 3 most relevant chunk indices (0-based), "
        f"most relevant first. Example: [2, 0, 4]\n\nChunks:\n{chunks_text}"
    )
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        })
        resp = _bedrock.invoke_model(
            modelId=_HAIKU, body=body,
            contentType="application/json", accept="application/json",
        )
        indices = json.loads(json.loads(resp["body"].read())["content"][0]["text"].strip())
        return [chunks[i] for i in indices if 0 <= i < len(chunks)]
    except Exception as e:
        logger.warning(f"Rerank failed ({e}), using top 3 by score.")
        return chunks[:3]


# ---------------------------------------------------------------------------
# Sonnet synthesis
# ---------------------------------------------------------------------------

def _synthesize(chunks: list[dict], context: str, trigger: str, customer_context: str) -> dict:
    grounding = "\n\n".join(
        f"Source: {c.get('url', '')}\nTitle: {c.get('title', '')}\n{c['text'][:500]}"
        for c in chunks
    )
    customer_section = (
        f"\nWhat we know about this customer from past meetings:\n{customer_context}\n"
        if customer_context else ""
    )
    prompt = (
        "You are a real-time AI assistant helping an AWS Solutions Architect "
        "during a live customer meeting.\n\n"
        f"Current meeting context:\n{context[:600]}\n"
        f"{customer_section}"
        f"What was just discussed: {trigger[:200]}\n\n"
        f"Relevant AWS knowledge:\n{grounding}\n\n"
        "Generate a proactive recommendation card. Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "brief title (max 10 words)",\n'
        '  "summary": "1-2 sentence answer directly addressing the meeting context",\n'
        '  "service_mentioned": ["list", "of", "aws", "services"],\n'
        '  "action_items": ["talking point 1", "point 2", "point 3"],\n'
        '  "source_urls": ["url1", "url2"],\n'
        '  "confidence": 0.85\n'
        "}\n\nBe specific, actionable, relevant to right now. No markdown."
    )
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        })
        resp = _bedrock.invoke_model(
            modelId=_SONNET, body=body,
            contentType="application/json", accept="application/json",
        )
        card = json.loads(json.loads(resp["body"].read())["content"][0]["text"].strip())
        card["id"] = str(uuid.uuid4())
        card["trigger"] = trigger[:100]
        return card
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return {
            "id": str(uuid.uuid4()),
            "title": "AWS Recommendation",
            "summary": f"Related to: {trigger[:100]}",
            "service_mentioned": [],
            "action_items": [],
            "source_urls": [c.get("url", "") for c in chunks[:2]],
            "confidence": 0.3,
            "trigger": trigger[:100],
        }


# ---------------------------------------------------------------------------
# AgentCore entrypoint
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()


@app.entrypoint
async def recommend(payload: dict):
    """Main handler invoked by AgentCore Runtime.

    Expected payload:
    {
        "context":          CCMState.to_dict() snapshot,
        "query":            trigger text / search query string,
        "customer_context": optional string of prior customer memory
    }
    """
    context_snapshot = payload.get("context", {})
    query = payload.get("query", "")
    customer_context = payload.get("customer_context", "")

    topics = context_snapshot.get("active_topics", [])
    services = context_snapshot.get("mentioned_services", {})

    context_str = (
        f"Topics: {', '.join(t['name'] for t in topics[:3])}\n"
        f"Services: {', '.join(services.keys())}\n"
        f"Goal: {context_snapshot.get('meeting_goal', '')}"
    )

    chunks = _retrieve_kb(query)
    if not chunks:
        yield {"error": "No KB results", "id": str(uuid.uuid4())}
        return

    top_chunks = _rerank(chunks, context_str, query)
    card = _synthesize(top_chunks, context_str, query, customer_context)
    yield card


if __name__ == "__main__":
    app.run()
