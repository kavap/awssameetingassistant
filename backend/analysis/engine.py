"""Cadence-based staged analysis engine.

Runs every ANALYZE_EVERY final transcript segments.
Two-phase per cycle:
  Phase 1 (Haiku)  — readiness check + search query generation
  Phase 2 (Sonnet) — staged analysis with accumulated KB context

Produces:
  Track A — autonomous analysis (always)
  Track B — directive-steered analysis (when SA directives exist)

Both tracks are broadcast over WebSocket as analysis_update / steered_analysis_update.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import boto3

from backend.config import settings
from .models import AnalysisResult, AnalysisStage, MEETING_TYPES
from .prompts import (
    QUERY_GEN_PROMPT,
    ANALYSIS_PROMPT,
    DIRECTIVE_EXTENSION,
    MEETING_TYPE_PROMPTS,
)

logger = logging.getLogger(__name__)

ANALYZE_EVERY = 3        # run a cycle every N final segments
MAX_TRANSCRIPT_SEGMENTS = 100
MAX_KB_RESULTS = 25

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
_bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# Low-level Bedrock helpers (sync — run in executor)
# ---------------------------------------------------------------------------

def _call_haiku(prompt: str, max_tokens: int = 300) -> str:
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = _bedrock.invoke_model(
        modelId=settings.bedrock_haiku_model,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["content"][0]["text"].strip()


def _call_sonnet(system: str, user: str, max_tokens: int = 1200) -> str:
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    })
    # Try configured model first; if ValidationException, try common fallback IDs
    model_candidates = [
        settings.bedrock_sonnet_model,
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_candidates = [m for m in model_candidates if not (m in seen or seen.add(m))]

    last_exc: Exception | None = None
    for model_id in unique_candidates:
        try:
            resp = _bedrock.invoke_model(
                modelId=model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            if model_id != settings.bedrock_sonnet_model:
                logger.warning(
                    f"Configured Sonnet model {settings.bedrock_sonnet_model!r} failed; "
                    f"using fallback {model_id!r}. Update BEDROCK_SONNET_MODEL in .env."
                )
            return json.loads(resp["body"].read())["content"][0]["text"].strip()
        except Exception as exc:
            if "ValidationException" in type(exc).__name__ or "invalid" in str(exc).lower():
                logger.debug(f"Model {model_id!r} rejected: {exc}")
                last_exc = exc
                continue
            raise  # non-validation errors propagate immediately
    raise last_exc  # all candidates failed


def _parse_json_safe(text: str) -> dict:
    """Extract JSON from text that may have markdown fences or preamble."""
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"No JSON in: {text[:200]!r}")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------------------
# Section extraction helpers
# ---------------------------------------------------------------------------

_SECTION_NAMES = (
    "Situation|Current State|Customer Needs|Open Questions"
    "|Proposed Solution Architecture|Key Recommendations|Sources|Architecture Diagram"
)
# Lookahead stops ONLY at the next known section header, not at any bold text inside content
_SECTION_RE = re.compile(
    rf"\*\*({_SECTION_NAMES}):\*\*\s*(.*?)(?=\*\*(?:{_SECTION_NAMES}):\*\*|$)",
    re.DOTALL,
)


def _extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for m in _SECTION_RE.finditer(text):
        key = m.group(1).strip()
        value = m.group(2).strip()
        sections[key] = value
        logger.debug(f"[section extracted] {key!r}: {len(value)} chars, preview={value[:80]!r}")
    if not sections:
        logger.warning(f"[section extraction] NO sections found. Raw first 300: {text[:300]!r}")
    return sections


def _extract_sources(sections: dict[str, str]) -> list[str]:
    raw = sections.get("Sources", "")
    return [u.strip() for u in re.findall(r"https?://\S+", raw)]


_GATHERING = "Gathering context — not enough signal yet."


def _build_result(
    raw: str,
    stage: AnalysisStage,
    ready: bool,
    reasoning: str,
    cycle_count: int,
    is_steered: bool,
) -> AnalysisResult:
    s = _extract_sections(raw)

    # Stage 1: never show architecture or diagram regardless of what Sonnet outputs
    if stage == 1:
        proposed = ""
        recommendations = ""
        mermaid = ""
    else:
        proposed = s.get("Proposed Solution Architecture", "")
        recommendations = s.get("Key Recommendations", "")
        # Stage 2: no diagram yet
        mermaid = s.get("Architecture Diagram", "") if stage == 3 else ""

    return AnalysisResult(
        stage=stage,
        ready=ready,
        reasoning=reasoning,
        situation=s.get("Situation", ""),
        current_state=s.get("Current State", ""),
        customer_needs=s.get("Customer Needs", ""),
        open_questions=s.get("Open Questions", ""),
        proposed_architecture=proposed,
        key_recommendations=recommendations,
        sources=_extract_sources(s),
        mermaid_diagram=mermaid,
        cycle_count=cycle_count,
        is_steered=is_steered,
    )


# ---------------------------------------------------------------------------
# AnalysisEngine
# ---------------------------------------------------------------------------

class AnalysisEngine:
    """Cadence-based analysis engine.

    Call on_final_segment() for every final transcript segment.
    Every ANALYZE_EVERY calls it automatically fires analyze_cycle().
    """

    def __init__(
        self,
        ws_manager,
        kb_retrieve,       # async callable: (query: str) -> list[dict]
        docs_search,       # async callable: (query: str) -> list[dict]
        meeting_type: str = "Customer Meeting",
        customer_context: str = "",
    ) -> None:
        self._ws = ws_manager
        self._kb_retrieve = kb_retrieve
        self._docs_search = docs_search
        self.meeting_type = meeting_type if meeting_type in MEETING_TYPES else "Customer Meeting"
        self._customer_context = customer_context

        # Session-level state
        self._transcript_segments: list[str] = []
        self._accumulated_kb: list[dict] = []
        self._seen_uris: set[str] = set()
        self._prior_queries: list[str] = []
        self._previous_analysis_a: str = ""
        self._previous_analysis_b: str = ""
        self._directives: list[str] = []
        self._cycle_count: int = 0
        self._segment_count: int = 0
        self._analyzing: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_directive(self, directive: str, ccm_state: dict | None = None) -> None:
        d = directive.strip()
        if d and d not in self._directives:
            self._directives.append(d)
            logger.info(f"SA directive added: {d!r}")
            # Immediately trigger a steered cycle if the engine is idle and has transcript
            if not self._analyzing and self._segment_count > 0:
                logger.info(f"[directive] triggering immediate cycle for Track B")
                asyncio.create_task(
                    self._analyze_cycle(ccm_state or {}),
                    name="directive-triggered-cycle",
                )

    async def on_final_segment(self, text: str, ccm_state: dict) -> None:
        """Called by the pipeline for every final transcript segment."""
        if text.strip():
            self._transcript_segments.append(text)
            if len(self._transcript_segments) > MAX_TRANSCRIPT_SEGMENTS:
                self._transcript_segments = self._transcript_segments[-MAX_TRANSCRIPT_SEGMENTS:]
            self._segment_count += 1
            logger.debug(
                f"[segment #{self._segment_count}] text={text[:60]!r} "
                f"analyzing={self._analyzing} "
                f"(next cycle at #{ANALYZE_EVERY * (self._segment_count // ANALYZE_EVERY + 1)})"
            )

        if self._segment_count % ANALYZE_EVERY == 0 and not self._analyzing:
            logger.info(
                f"[cycle trigger] segment #{self._segment_count} → firing analysis cycle"
            )
            asyncio.create_task(self._analyze_cycle(ccm_state))

    def reset(self) -> None:
        self._transcript_segments = []
        self._accumulated_kb = []
        self._seen_uris = set()
        self._prior_queries = []
        self._previous_analysis_a = ""
        self._previous_analysis_b = ""
        self._directives = []
        self._cycle_count = 0
        self._segment_count = 0
        self._analyzing = False

    # ------------------------------------------------------------------
    # Internal cycle
    # ------------------------------------------------------------------

    async def _analyze_cycle(self, ccm_state: dict) -> None:
        if self._analyzing:
            return
        self._analyzing = True
        try:
            self._cycle_count += 1
            logger.info(f"Analysis cycle {self._cycle_count} starting "
                        f"({self._segment_count} segments so far)")

            # Phase 1 — readiness + query generation
            ready, reasoning, new_queries = await self._phase1_query_gen(ccm_state)

            # Phase 2 — KB retrieval for new queries (accumulate)
            if ready and new_queries:
                await self._phase2_accumulate_kb(new_queries)

            # Phase 3 — staged analysis (Track A)
            stage = self._determine_stage(ready)
            logger.info(
                f"[cycle {self._cycle_count}] stage={stage} segments={self._segment_count} "
                f"kb_chunks={len(self._accumulated_kb)} directives={len(self._directives)}"
            )
            result_a = await self._phase3_analysis(
                stage, ready, reasoning, is_steered=False
            )
            self._previous_analysis_a = self._result_to_markdown(result_a)
            payload_a = result_a.to_dict()
            logger.info(
                f"[broadcast] analysis_update stage={payload_a['stage']} "
                f"cycle={payload_a['cycle_count']} "
                f"fields_nonempty={[k for k,v in payload_a.items() if v and k not in ('id','timestamp','stage','cycle_count','ready','is_steered')]}"
            )
            await self._ws.broadcast({
                "type": "analysis_update",
                "ts": time.time(),
                "payload": payload_a,
            })
            logger.info("[broadcast] analysis_update sent to WS manager")

            # Track B — run only when directives exist
            if self._directives:
                result_b = await self._phase3_analysis(
                    stage, ready, reasoning, is_steered=True
                )
                self._previous_analysis_b = self._result_to_markdown(result_b)
                payload_b = result_b.to_dict()
                logger.info(
                    f"[broadcast] steered_analysis_update stage={payload_b['stage']} "
                    f"cycle={payload_b['cycle_count']}"
                )
                await self._ws.broadcast({
                    "type": "steered_analysis_update",
                    "ts": time.time(),
                    "payload": payload_b,
                })
                logger.info("[broadcast] steered_analysis_update sent")

        except Exception as e:
            logger.error(f"Analysis cycle error: {e}", exc_info=True)
        finally:
            self._analyzing = False

    # ------------------------------------------------------------------
    # Phase 1 — readiness + query gen (Haiku)
    # ------------------------------------------------------------------

    async def _phase1_query_gen(
        self, ccm_state: dict
    ) -> tuple[bool, str, list[str]]:
        transcript_text = "\n".join(self._transcript_segments[-30:])

        known_services = list(ccm_state.get("mentioned_services", {}).keys())
        known_topics = [t["name"] for t in ccm_state.get("active_topics", [])]
        known_context = ", ".join(known_services + known_topics) or "none yet"
        prior_queries_str = "\n".join(f"- {q}" for q in self._prior_queries) or "none"

        prompt = QUERY_GEN_PROMPT.format(
            transcript=transcript_text[:3000],
            known_context=known_context,
            prior_queries=prior_queries_str,
        )

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(_executor, partial(_call_haiku, prompt, 400))
            logger.debug(f"[phase1 haiku raw] {raw[:300]!r}")
            parsed = _parse_json_safe(raw)
            ready = bool(parsed.get("ready", False))
            reasoning = parsed.get("reasoning", "")
            new_queries: list[str] = parsed.get("new_queries", [])
            # Deduplicate against prior queries
            new_queries = [
                q for q in new_queries
                if q not in self._prior_queries
            ]
            self._prior_queries.extend(new_queries)
            logger.info(
                f"[phase1 result] cycle={self._cycle_count} ready={ready} "
                f"reasoning={reasoning[:100]!r} new_queries={new_queries}"
            )
            return ready, reasoning, new_queries
        except Exception as e:
            logger.warning(f"[phase1 FAILED] {e}", exc_info=True)
            return False, str(e), []

    # ------------------------------------------------------------------
    # Phase 2 — KB accumulation
    # ------------------------------------------------------------------

    async def _phase2_accumulate_kb(self, queries: list[str]) -> None:
        tasks = []
        for q in queries:
            tasks.append(self._kb_retrieve(q))
            tasks.append(self._docs_search(q))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        new_count = 0
        for results in all_results:
            if isinstance(results, Exception):
                continue
            for r in results:
                uri = r.get("url", "") or r.get("uri", "")
                if uri and uri not in self._seen_uris:
                    self._seen_uris.add(uri)
                    self._accumulated_kb.append(r)
                    new_count += 1

        # Keep top MAX_KB_RESULTS by score
        self._accumulated_kb.sort(key=lambda x: -x.get("score", 0.0))
        self._accumulated_kb = self._accumulated_kb[:MAX_KB_RESULTS]
        top_urls = [r.get("url", r.get("uri", "?"))[:60] for r in self._accumulated_kb[:5]]
        logger.info(
            f"[phase2 KB] +{new_count} new chunks, {len(self._accumulated_kb)} total. "
            f"Top URIs: {top_urls}"
        )

    # ------------------------------------------------------------------
    # Phase 3 — staged analysis (Sonnet)
    # ------------------------------------------------------------------

    async def _phase3_analysis(
        self,
        stage: AnalysisStage,
        ready: bool,
        reasoning: str,
        is_steered: bool,
    ) -> AnalysisResult:
        stage_labels = {
            1: "STAGE 1 — Gathering context, do not speculate",
            2: "STAGE 2 — Direction emerging, use [ASSUMPTION: ...] for anything unconfirmed",
            3: "STAGE 3 — Clear picture, provide full architecture and recommendations",
        }
        stage_label = stage_labels[stage]

        transcript_text = "\n".join(self._transcript_segments[-50:])

        kb_lines = []
        for r in self._accumulated_kb[:12]:
            url = r.get("url", r.get("uri", ""))
            title = r.get("title", url)
            text = r.get("text", "")[:300]
            kb_lines.append(f"Source: {url}\nTitle: {title}\n{text}")
        kb_context = "\n---\n".join(kb_lines) if kb_lines else "No KB results yet."

        customer_ctx = (
            f"\nCustomer context from prior meetings:\n{self._customer_context}\n"
            if self._customer_context else ""
        )

        previous = self._previous_analysis_b if is_steered and self._previous_analysis_b \
            else self._previous_analysis_a
        # Cap previous analysis to avoid consuming too much of the output budget
        if previous and len(previous) > 2500:
            previous = previous[:2500] + "\n[... truncated for brevity ...]"
        previous_section = previous if previous else "No prior analysis — this is the first cycle."

        user_prompt = ANALYSIS_PROMPT.format(
            stage_label=stage_label,
            previous_analysis=previous_section,
            segment_count=len(self._transcript_segments),
            transcript=transcript_text[:4000],
            kb_context=kb_context,
            customer_context_section=customer_ctx,
        )

        if is_steered and self._directives:
            directives_list = "\n".join(f"- {d}" for d in self._directives)
            user_prompt += DIRECTIVE_EXTENSION.format(directives_list=directives_list)

        role_prefix = MEETING_TYPE_PROMPTS.get(self.meeting_type, "")

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                _executor,
                partial(_call_sonnet, role_prefix, user_prompt, 4096),
            )
            logger.debug(f"[phase3 sonnet raw first 2000] {raw[:2000]!r}")
            result = _build_result(raw, stage, ready, reasoning,
                                   self._cycle_count, is_steered)
            track = "B" if is_steered else "A"
            logger.info(
                f"[phase3 result] cycle={self._cycle_count} track={track} stage={stage} "
                f"situation_len={len(result.situation)} current_state_len={len(result.current_state)} "
                f"customer_needs_len={len(result.customer_needs)} sources={len(result.sources)}"
            )
            return result
        except Exception as e:
            logger.error(f"[phase3 FAILED] {e}", exc_info=True)
            return AnalysisResult(
                stage=stage,
                ready=ready,
                reasoning=reasoning,
                situation="Analysis failed — see backend logs.",
                cycle_count=self._cycle_count,
                is_steered=is_steered,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _determine_stage(self, ready: bool) -> AnalysisStage:
        # Stage 1: < 6 segments or not ready (gathering context)
        if not ready or self._segment_count < 6:
            return 1
        # Stage 2: 6-14 segments (direction emerging, tentative architecture)
        if self._segment_count < 15:
            return 2
        # Stage 3: 15+ segments (full architecture, recommendations, diagram)
        return 3

    @staticmethod
    def _result_to_markdown(r: AnalysisResult) -> str:
        parts = []
        if r.situation:
            parts.append(f"**Situation:**\n{r.situation}")
        if r.current_state:
            parts.append(f"**Current State:**\n{r.current_state}")
        if r.customer_needs:
            parts.append(f"**Customer Needs:**\n{r.customer_needs}")
        if r.open_questions:
            parts.append(f"**Open Questions:**\n{r.open_questions}")
        if r.proposed_architecture:
            parts.append(f"**Proposed Solution Architecture:**\n{r.proposed_architecture}")
        if r.key_recommendations:
            parts.append(f"**Key Recommendations:**\n{r.key_recommendations}")
        if r.sources:
            parts.append(f"**Sources:**\n" + "\n".join(r.sources))
        if r.mermaid_diagram:
            parts.append(f"**Architecture Diagram:**\n{r.mermaid_diagram}")
        return "\n\n".join(parts)
