"""AgentCore Memory — persist customer context across meetings.

Short-term: session events written during a meeting.
Long-term:  semantic memory records extracted by AgentCore Memory strategies
            and retrieved at session start to prime the Recommendation Agent.

Two boto3 clients:
  bedrock-agentcore-control  → create/manage Memory resources
  bedrock-agentcore          → read/write events and memory records
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial

import boto3

from backend.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agentcore-memory")
_dp_client = boto3.client("bedrock-agentcore", region_name=settings.aws_region)


def is_configured() -> bool:
    return bool(settings.agentcore_memory_id)


# ---------------------------------------------------------------------------
# Read: load prior customer context at meeting start
# ---------------------------------------------------------------------------

def _retrieve_sync(customer_id: str, query: str) -> list[dict]:
    namespace = f"/strategy/{settings.agentcore_memory_strategy_id}/actor/{customer_id}/"
    resp = _dp_client.retrieve_memory_records(
        memoryId=settings.agentcore_memory_id,
        namespace=namespace,
        query=query,
        maxResults=10,
    )
    return resp.get("memoryRecords", [])


async def load_customer_context(customer_id: str) -> str:
    """Retrieve relevant past context for this customer.

    Returns a plain-text summary string to inject into the recommendation prompt.
    Returns empty string if memory not configured or customer is unknown.
    """
    if not is_configured() or customer_id == "anonymous":
        return ""

    loop = asyncio.get_event_loop()
    try:
        records = await loop.run_in_executor(
            _executor,
            partial(
                _retrieve_sync,
                customer_id,
                "AWS services, architecture, pain points, preferences, open questions",
            ),
        )
        if not records:
            return ""

        lines = []
        for r in records:
            rec = r.get("memoryRecord", {})
            fact = rec.get("fact", "")
            score = r.get("relevanceScore", 0.0)
            if fact and score > 0.5:
                lines.append(f"- {fact}")

        result = "\n".join(lines[:8])
        logger.info(f"Loaded {len(lines)} memory records for customer '{customer_id}'")
        return result

    except Exception as e:
        logger.warning(f"Memory load failed for '{customer_id}': {e}")
        return ""


# ---------------------------------------------------------------------------
# Write: save key events during/after a meeting
# ---------------------------------------------------------------------------

def _create_event_sync(customer_id: str, session_id: str, text: str, role: str) -> None:
    _dp_client.create_event(
        memoryId=settings.agentcore_memory_id,
        actorId=customer_id,
        sessionId=session_id,
        eventTimestamp=datetime.now(timezone.utc).isoformat(),
        payload=[
            {
                "conversational": {
                    "content": {"text": text},
                    "role": role,   # USER | ASSISTANT
                }
            }
        ],
    )


async def save_session_event(
    customer_id: str,
    session_id: str,
    text: str,
    role: str = "USER",
) -> None:
    """Write a conversation event to Memory (feeds long-term extraction pipeline)."""
    if not is_configured() or customer_id == "anonymous":
        return

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            _executor,
            partial(_create_event_sync, customer_id, session_id, text, role),
        )
    except Exception as e:
        logger.warning(f"Memory write failed for '{customer_id}': {e}")


async def save_session_summary(
    customer_id: str,
    session_id: str,
    ccm_state: dict,
) -> None:
    """Write a structured meeting summary as a Memory event at session end.

    AgentCore Memory's extraction strategies will consolidate this into
    long-term semantic records for future retrieval.
    """
    if not is_configured() or customer_id == "anonymous":
        return

    services = list(ccm_state.get("mentioned_services", {}).keys())
    topics = [t["name"] for t in ccm_state.get("active_topics", [])]
    questions = [q["text"] for q in ccm_state.get("open_questions", []) if not q.get("resolved")]
    goal = ccm_state.get("meeting_goal", "")

    summary = (
        f"Meeting summary for customer '{customer_id}' (session {session_id[:8]}):\n"
        f"Goal: {goal}\n"
        f"AWS services discussed: {', '.join(services) or 'none'}\n"
        f"Topics: {', '.join(topics) or 'none'}\n"
        f"Open questions: {'; '.join(questions[:5]) or 'none'}"
    )

    await save_session_event(customer_id, session_id, summary, role="ASSISTANT")
    logger.info(f"Session summary written to Memory for customer '{customer_id}'")
