"""AgentCore Runtime client — called by FastAPI to invoke the deployed agent.

Falls back gracefully if AGENTCORE_RUNTIME_ARN is not configured.
"""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import boto3

from backend.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agentcore-invoke")
_client = boto3.client("bedrock-agentcore", region_name=settings.aws_region)


def is_configured() -> bool:
    return bool(settings.agentcore_runtime_arn)


def _invoke_sync(payload: dict, session_id: str) -> dict | None:
    """Synchronous AgentCore Runtime invocation — run in thread executor."""
    response = _client.invoke_agent_runtime(
        agentRuntimeArn=settings.agentcore_runtime_arn,
        payload=json.dumps(payload).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
        runtimeSessionId=session_id,
    )
    raw = response["response"].read()
    return json.loads(raw)


async def invoke_recommendation(
    context_snapshot: dict,
    query: str,
    session_id: str,
    customer_context: str = "",
) -> dict | None:
    """Invoke the AgentCore Recommendation Agent asynchronously.

    Returns the recommendation card dict, or None on failure.
    """
    if not is_configured():
        logger.debug("AGENTCORE_RUNTIME_ARN not set — AgentCore invocation skipped.")
        return None

    payload = {
        "context": context_snapshot,
        "query": query,
        "customer_context": customer_context,
    }

    loop = asyncio.get_event_loop()
    try:
        card = await loop.run_in_executor(
            _executor, partial(_invoke_sync, payload, session_id)
        )
        return card
    except Exception as e:
        logger.error(f"AgentCore invocation failed: {e}")
        return None
