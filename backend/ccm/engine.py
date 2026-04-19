"""Conversation Context Map engine — powered by Claude Haiku.

Each final transcript segment is sent to Haiku with a compact prompt.
Haiku returns structured JSON: services, competitors, questions, topics, goal.
Partial segments are skipped (no Haiku call, no I/O overhead).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

from backend.config import settings
from .models import CCMState, CCMUpdateEvent, MentionedService, OpenQuestion, Topic

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ccm-haiku")
_bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

# ---------------------------------------------------------------------------
# Haiku prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a real-time context extraction engine for an AWS Solutions Architect "
    "meeting assistant. Extract structured facts from each transcript segment. "
    "Respond with ONLY valid JSON — no markdown fences, no explanation."
)

_PROMPT_TEMPLATE = """\
Analyze this AWS customer meeting transcript segment.

Segment: "{text}"

Prior context:
- AWS services already noted: {known_aws}
- Competitors/tools already noted: {known_comp}
- Active topics: {active_topics}
- Meeting goal so far: "{meeting_goal}"

Return JSON matching this schema exactly (no extra keys):
{{
  "aws_services": ["AWS service names mentioned or clearly implied in this segment"],
  "competitors": ["non-AWS cloud providers, databases, or tools mentioned"],
  "questions": ["questions raised in this segment, verbatim or close paraphrase"],
  "topics": ["1-3 of: data_warehouse, data_lake, streaming, machine_learning, migration, cost_optimization, security, serverless, networking, database, comparison, architecture, governance, performance"],
  "meeting_goal": "one sentence if this segment clarifies the meeting purpose, else empty string",
  "should_recommend": true
}}

Set should_recommend=true when the segment contains a question, a new service/architecture mention, or a decision point worth surfacing a recommendation for."""


# ---------------------------------------------------------------------------
# Haiku call (sync — runs in executor)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract JSON object from text that may have markdown fences or preamble."""
    text = text.strip()
    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    # Find first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in response: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def _call_haiku_sync(prompt: str) -> dict:
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "temperature": 0.0,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = _bedrock_client.invoke_model(
        modelId=settings.bedrock_haiku_model,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    raw = json.loads(resp["body"].read())["content"][0]["text"]
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jaccard(a: str, b: str) -> float:
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CCMEngine:
    """Stateful Conversation Context Map engine.

    process_transcript_segment is async: partial segments return immediately,
    final segments call Haiku in a thread executor (~300-600ms round-trip).
    """

    def __init__(self) -> None:
        self._state = CCMState()

    @property
    def state(self) -> CCMState:
        return self._state

    def reset(self) -> None:
        self._state = CCMState()

    async def process_transcript_segment(
        self, text: str, is_final: bool
    ) -> CCMUpdateEvent | None:
        """Process one transcript segment.

        Partial results are ignored (Haiku would see incomplete sentences).
        Final results are sent to Haiku for structured extraction.
        Returns a CCMUpdateEvent when something significant was detected.
        """
        if not text.strip():
            return None

        if not is_final:
            return None  # Skip partials — Haiku sees final sentences only

        # Append to transcript history
        self._state.full_transcript.append(text)

        # Build context summary for the prompt
        known_aws = [
            s.name for s in self._state.mentioned_services.values()
            if s.category == "aws"
        ]
        known_comp = [
            s.name for s in self._state.mentioned_services.values()
            if s.category == "competitor"
        ]

        prompt = _PROMPT_TEMPLATE.format(
            text=text[:500],
            known_aws=", ".join(known_aws[-10:]) or "none",
            known_comp=", ".join(known_comp[-5:]) or "none",
            active_topics=", ".join(t.name for t in self._state.active_topics) or "none",
            meeting_goal=self._state.meeting_goal or "unknown",
        )

        loop = asyncio.get_event_loop()
        try:
            extracted = await loop.run_in_executor(_executor, _call_haiku_sync, prompt)
        except Exception as e:
            logger.warning(f"CCM Haiku extraction failed: {e}")
            return None

        event_type: str | None = None

        # AWS services
        for name in extracted.get("aws_services", []):
            name = name.strip()
            if not name:
                continue
            key = name.lower()
            if key in self._state.mentioned_services:
                self._state.mentioned_services[key].mention_count += 1
                self._state.mentioned_services[key].last_seen_at = time.time()
            else:
                self._state.mentioned_services[key] = MentionedService(
                    name=name, category="aws"
                )
                event_type = "service_mentioned"

        # Competitors / third-party tools
        for name in extracted.get("competitors", []):
            name = name.strip()
            if not name:
                continue
            key = name.lower()
            if key in self._state.mentioned_services:
                self._state.mentioned_services[key].mention_count += 1
                self._state.mentioned_services[key].last_seen_at = time.time()
            else:
                self._state.mentioned_services[key] = MentionedService(
                    name=name, category="competitor"
                )
                if event_type is None:
                    event_type = "competitor_mentioned"

        # Questions — deduplicate by Jaccard similarity
        for q_text in extracted.get("questions", []):
            q_text = q_text.strip()
            if not q_text:
                continue
            is_dup = any(
                _jaccard(q.text, q_text) > 0.5
                for q in self._state.open_questions
                if not q.resolved
            )
            if not is_dup:
                self._state.open_questions.append(OpenQuestion(text=q_text))
                if event_type is None:
                    event_type = "question_detected"

        # Topics — accumulate confidence on repeated mentions
        for topic_name in extracted.get("topics", []):
            topic_name = topic_name.strip()
            if not topic_name:
                continue
            existing = next(
                (t for t in self._state.active_topics if t.name == topic_name), None
            )
            if existing:
                existing.confidence = min(existing.confidence + 0.1, 1.0)
                existing.last_seen_at = time.time()
            else:
                self._state.active_topics.append(
                    Topic(name=topic_name, confidence=0.7)
                )
                if event_type is None:
                    event_type = "topic_shift"
            # Keep top 5 by confidence
            self._state.active_topics.sort(key=lambda t: -t.confidence)
            self._state.active_topics = self._state.active_topics[:5]

        # Meeting goal — capture once from early segments
        goal = extracted.get("meeting_goal", "").strip()
        if goal and not self._state.meeting_goal:
            self._state.meeting_goal = goal

        self._state.last_updated_at = time.time()

        # Haiku flagged this as recommendation-worthy even without a new entity
        if extracted.get("should_recommend") and event_type is None:
            event_type = "topic_shift"

        if event_type:
            self._state.recommendation_trigger_count += 1
            return CCMUpdateEvent(
                event_type=event_type,  # type: ignore[arg-type]
                session_id=self._state.session_id,
                context_snapshot=self._state.to_dict(),
                trigger_text=text[:200],
            )

        return None

    def get_state_snapshot(self) -> dict:
        return self._state.to_dict()
