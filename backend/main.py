"""FastAPI application — main entry point."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agentcore import client as agentcore_client
from backend.agentcore import memory as agentcore_memory
from backend.agent.recommendation_agent import RecommendationAgent
from backend import storage
from backend.analysis.engine import AnalysisEngine
from backend.analysis.models import MEETING_TYPES
from backend.audio.capture import get_capture
from backend.ccm.engine import CCMEngine
from backend.config import settings
from backend.knowledge_base import bedrock_kb
from backend.knowledge_base.bedrock_kb import retrieve as kb_retrieve
from backend.knowledge_base.docs_search import search_aws_docs
from backend.websocket.manager import manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Set analysis pipeline loggers to DEBUG for full visibility
logging.getLogger("backend.analysis.engine").setLevel(logging.DEBUG)
logging.getLogger("backend.main").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

ccm_engine = CCMEngine()
event_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
recommendation_agent = RecommendationAgent(ws_manager, event_queue)

# AnalysisEngine is recreated on each meeting start (holds session state)
analysis_engine: AnalysisEngine | None = None

_meeting_task: asyncio.Task | None = None
_stop_event: asyncio.Event = asyncio.Event()
_session_id: str | None = None
_customer_id: str = "anonymous"
_meeting_type: str = "Customer Meeting"
_meeting_name: str = ""
_participants: list[str] = []
_selected_roles: list[str] = []
_speaker_mapping: dict[str, dict] = {}
_customer_context: str = ""

# Per-topic cooldown for AgentCore fast-card path
_last_trigger: dict[str, float] = {}
COOLDOWN_SECONDS = 20


# ---------------------------------------------------------------------------
# STT provider selection
# ---------------------------------------------------------------------------

def _get_stream_transcription_fn():
    provider = settings.stt_provider.lower()
    if provider == "whisper":
        logger.info("STT provider: faster-whisper (local)")
        from backend.transcription.whisper_stream import stream_transcription
        return stream_transcription
    else:
        logger.info("STT provider: Amazon Transcribe Streaming (cloud)")
        from backend.transcription.transcribe_stream import stream_transcription
        return stream_transcription


# ---------------------------------------------------------------------------
# AgentCore fast-card dispatcher (per CCM event, fire-and-forget)
# ---------------------------------------------------------------------------

async def _dispatch_recommendation(ccm_event) -> None:
    """Fast-path: invoke AgentCore Runtime and broadcast a quick recommendation card."""
    ctx = ccm_event.context_snapshot
    topics = ctx.get("active_topics", [])
    topic_key = topics[0]["name"] if topics else "general"

    if time.time() - _last_trigger.get(topic_key, 0) < COOLDOWN_SECONDS:
        return
    _last_trigger[topic_key] = time.time()

    aws_svcs = [
        k for k, v in ctx.get("mentioned_services", {}).items()
        if v["category"] == "aws"
    ]
    query_parts = []
    if topics:
        query_parts.append(topics[0]["name"].replace("_", " "))
    if aws_svcs:
        query_parts.append(" ".join(aws_svcs[:3]))
    query_parts.append(ccm_event.trigger_text[:100])
    query = " ".join(query_parts)[:300]

    card = await agentcore_client.invoke_recommendation(
        context_snapshot=ctx,
        query=query,
        session_id=_session_id or "no-session",
        customer_context=_customer_context,
        meeting_type=_meeting_type,
    )

    if card and "error" not in card:
        await ws_manager.broadcast({
            "type": "recommendation",
            "ts": time.time(),
            "payload": card,
        })
        logger.info(f"AgentCore recommendation emitted: {card.get('title', '')}")

        if _customer_id != "anonymous":
            await agentcore_memory.save_session_event(
                _customer_id,
                _session_id or "no-session",
                ccm_event.trigger_text,
                role="USER",
            )


async def handle_ccm_event(ccm_event) -> None:
    """Route a CCMUpdateEvent to AgentCore (fast card) or local agent, and broadcast CCM state."""
    await ws_manager.broadcast({
        "type": "ccm_update",
        "ts": time.time(),
        "payload": ccm_event.context_snapshot,
    })

    if agentcore_client.is_configured():
        asyncio.create_task(
            _dispatch_recommendation(ccm_event),
            name="agentcore-recommend",
        )
    else:
        try:
            event_queue.put_nowait(ccm_event)
        except asyncio.QueueFull:
            try:
                event_queue.get_nowait()
                event_queue.put_nowait(ccm_event)
            except asyncio.QueueEmpty:
                pass


async def handle_final_transcript(text: str, speaker: str | None = None) -> None:
    """Called for every final transcript segment — feeds the AnalysisEngine cadence."""
    logger.debug(f"[handle_final_transcript] engine={analysis_engine is not None} text={text[:60]!r} speaker={speaker}")
    if analysis_engine is not None:
        await analysis_engine.on_final_segment(text, ccm_engine.get_state_snapshot(), speaker=speaker)
    else:
        logger.warning("[handle_final_transcript] analysis_engine is None — segment dropped")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    env_file = os.path.abspath(".env")
    env_loaded = os.path.exists(env_file)
    logger.info("Starting Meeting Intelligence Assistant backend...")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f".env file: {env_file} ({'FOUND' if env_loaded else 'NOT FOUND — run from project root!'})")
    logger.info(f"STT provider: {settings.stt_provider}")
    logger.info(f"Bedrock Haiku model: {settings.bedrock_haiku_model}")
    logger.info(f"Bedrock Sonnet model: {settings.bedrock_sonnet_model}")

    if bedrock_kb.is_configured():
        logger.info(f"Bedrock KB: {settings.bedrock_kb_id} ({settings.bedrock_kb_search_type})")
    else:
        logger.warning(
            "BEDROCK_KB_ID not set — KB retrieval disabled. "
            "Run scripts/setup_kb.py then set BEDROCK_KB_ID in .env."
        )

    if agentcore_client.is_configured():
        logger.info(f"AgentCore Runtime: {settings.agentcore_runtime_arn}")
    else:
        logger.info("AGENTCORE_RUNTIME_ARN not set — using local RecommendationAgent.")
        recommendation_agent.start()

    if agentcore_memory.is_configured():
        logger.info(f"AgentCore Memory: {settings.agentcore_memory_id}")
    else:
        logger.info("AGENTCORE_MEMORY_ID not set — cross-session memory disabled.")

    yield

    if not agentcore_client.is_configured():
        recommendation_agent.stop()
    if _meeting_task and not _meeting_task.done():
        _meeting_task.cancel()
    logger.info("Backend shutdown complete.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Meeting Intelligence Assistant",
    description="Real-time AWS meeting assistant backend",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class StartMeetingRequest(BaseModel):
    customer_id: str = "anonymous"
    meeting_type: str = "Customer Meeting"
    meeting_name: str = ""
    participants: list[str] = []
    selected_roles: list[str] = []


class DirectiveRequest(BaseModel):
    directive: str


class SpeakerMappingRequest(BaseModel):
    mappings: dict  # {"spk_0": {"name": "...", "org": "...", "role": "..."}, ...}


class SpeakerCorrectionRequest(BaseModel):
    corrections: list[dict]  # [{"index": int, "speaker_id": str}, ...]


class SaveMeetingRequest(BaseModel):
    session_id: str
    customer_id: str = "anonymous"
    meeting_type: str = "Customer Meeting"
    meeting_name: str = ""
    participants: list[str] = []
    selected_roles: list[str] = []
    speaker_mapping: dict = {}
    started_at: float = 0.0
    stopped_at: float = 0.0
    transcript: list[dict] = []
    analysis_track_a: dict | None = None
    analysis_track_b: dict | None = None
    recommendations: list[dict] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "stt_provider": settings.stt_provider,
        "bedrock_kb_configured": bedrock_kb.is_configured(),
        "bedrock_kb_id": settings.bedrock_kb_id or None,
        "agentcore_runtime_configured": agentcore_client.is_configured(),
        "agentcore_memory_configured": agentcore_memory.is_configured(),
        "ws_clients": ws_manager.connection_count,
        "session_id": _session_id,
        "customer_id": _customer_id,
        "meeting_type": _meeting_type,
    }


@app.get("/meeting/types")
async def get_meeting_types():
    return {"types": MEETING_TYPES}


@app.get("/meeting/state")
async def get_meeting_state():
    return ccm_engine.get_state_snapshot()


@app.get("/meeting/config")
async def get_meeting_config():
    """Return frontend configuration: roles, role descriptions, and canned directives."""
    from backend.roles import ROLE_DESCRIPTIONS
    roles = [r.strip() for r in settings.default_meeting_roles.split(",") if r.strip()]
    directives = [d.strip() for d in settings.default_directives.split(",") if d.strip()]
    return {
        "default_roles": roles,
        "role_descriptions": ROLE_DESCRIPTIONS,
        "default_directives": directives,
    }


@app.post("/meeting/start")
async def start_meeting(body: StartMeetingRequest = StartMeetingRequest()):
    global _meeting_task, _stop_event, _session_id, _customer_id, _meeting_type
    global _meeting_name, _participants, _selected_roles, _speaker_mapping
    global _customer_context, _last_trigger, analysis_engine

    if _meeting_task and not _meeting_task.done():
        return JSONResponse(
            status_code=409,
            content={"error": "Meeting already in progress. Stop it first."},
        )

    ccm_engine.reset()
    _stop_event = asyncio.Event()
    _session_id = str(uuid.uuid4())
    _customer_id = (body.customer_id or "anonymous").strip().lower()
    _meeting_type = body.meeting_type if body.meeting_type in MEETING_TYPES else "Customer Meeting"
    _meeting_name = body.meeting_name.strip()
    _participants = [p.strip() for p in body.participants if p.strip()]
    _selected_roles = [r.strip() for r in body.selected_roles if r.strip()]
    _speaker_mapping = {}
    _last_trigger = {}

    # Load prior customer context from AgentCore Memory
    _customer_context = await agentcore_memory.load_customer_context(_customer_id)
    if _customer_context:
        logger.info(f"Loaded prior context for customer '{_customer_id}'")

    # Create fresh AnalysisEngine for this session
    analysis_engine = AnalysisEngine(
        ws_manager=ws_manager,
        kb_retrieve=kb_retrieve,
        docs_search=search_aws_docs,
        meeting_type=_meeting_type,
        customer_context=_customer_context,
    )

    capture = get_capture(None)
    audio_gen = capture.audio_generator()
    stream_fn = _get_stream_transcription_fn()

    async def run_pipeline():
        await stream_fn(
            audio_gen=audio_gen,
            ccm_engine=ccm_engine,
            ws_manager=ws_manager,
            event_queue=event_queue,
            stop_event=_stop_event,
            on_ccm_event=handle_ccm_event,
            on_final_transcript=handle_final_transcript,
        )

    _meeting_task = asyncio.create_task(run_pipeline(), name="meeting-pipeline")

    await ws_manager.broadcast({
        "type": "meeting_started",
        "ts": time.time(),
        "payload": {
            "session_id": _session_id,
            "customer_id": _customer_id,
            "meeting_type": _meeting_type,
            "meeting_name": _meeting_name,
            "participants": _participants,
            "selected_roles": _selected_roles,
            "stt_provider": settings.stt_provider,
            "customer_context_loaded": bool(_customer_context),
        },
    })

    logger.info(
        f"Meeting started. Session: {_session_id}, "
        f"Customer: {_customer_id}, Type: {_meeting_type}"
    )
    return {
        "session_id": _session_id,
        "customer_id": _customer_id,
        "meeting_type": _meeting_type,
        "status": "started",
        "stt_provider": settings.stt_provider,
        "customer_context_loaded": bool(_customer_context),
    }


@app.post("/meeting/stop")
async def stop_meeting():
    global _meeting_task, _stop_event, _session_id

    _stop_event.set()
    if _meeting_task and not _meeting_task.done():
        _meeting_task.cancel()

    if _session_id and _customer_id != "anonymous":
        await agentcore_memory.save_session_summary(
            _customer_id,
            _session_id,
            ccm_engine.get_state_snapshot(),
        )

    await ws_manager.broadcast({
        "type": "meeting_stopped",
        "ts": time.time(),
        "payload": {"session_id": _session_id, "customer_id": _customer_id},
    })

    logger.info(f"Meeting stopped. Session: {_session_id}, Customer: {_customer_id}")
    _session_id = None
    return {"status": "stopped"}


@app.post("/meeting/reset")
async def reset_meeting():
    global analysis_engine
    ccm_engine.reset()
    if analysis_engine is not None:
        analysis_engine.reset()
    return {"status": "reset", "session_id": ccm_engine.state.session_id}


@app.post("/meeting/directive")
async def add_directive(body: DirectiveRequest):
    """Inject an SA directive into the analysis engine (Track B steering)."""
    if not body.directive.strip():
        return JSONResponse(status_code=400, content={"error": "directive is required"})
    if analysis_engine is None:
        return JSONResponse(status_code=409, content={"error": "No active meeting session"})

    analysis_engine.add_directive(body.directive.strip(), ccm_engine.get_state_snapshot())
    logger.info(f"SA directive injected: {body.directive!r}")
    return {"status": "ok", "directive": body.directive.strip()}


@app.post("/meeting/speaker-mapping")
async def set_speaker_mapping(body: SpeakerMappingRequest):
    """SA-provided speaker→participant mapping. Triggers immediate re-analysis."""
    global _speaker_mapping
    if analysis_engine is None:
        return JSONResponse(status_code=409, content={"error": "No active meeting session"})

    _speaker_mapping = body.mappings
    analysis_engine.update_speaker_mapping(_speaker_mapping)

    await ws_manager.broadcast({
        "type": "speaker_mapping_update",
        "ts": time.time(),
        "payload": {"mappings": _speaker_mapping},
    })
    logger.info(f"Speaker mapping updated: {list(_speaker_mapping.keys())}")
    return {"status": "ok", "mapped_speakers": list(_speaker_mapping.keys())}


@app.post("/transcript/speaker-corrections")
async def apply_speaker_corrections(body: SpeakerCorrectionRequest):
    """SA-provided per-segment speaker re-attribution.
    Updates backend transcript segments without triggering immediate re-analysis.
    Corrections are picked up in the next natural analysis cycle.
    """
    if analysis_engine is None:
        return JSONResponse(status_code=409, content={"error": "No active meeting session"})
    analysis_engine.apply_speaker_corrections(body.corrections)
    return {"status": "ok", "applied": len(body.corrections)}


@app.post("/meetings/save")
async def save_meeting(body: SaveMeetingRequest):
    """Persist full meeting snapshot sent by the frontend on stop."""
    try:
        storage.save_meeting(body.model_dump())
        logger.info(f"Meeting saved: {body.session_id} ({len(body.transcript)} transcript chunks)")
        return {"status": "saved", "session_id": body.session_id}
    except Exception as e:
        logger.error(f"Failed to save meeting: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/meetings")
async def list_meetings():
    """List all saved meetings (index entries, no full content)."""
    return {"meetings": storage.list_meetings()}


@app.get("/meetings/{session_id}")
async def get_meeting(session_id: str):
    """Return full saved meeting record."""
    record = storage.get_meeting(session_id)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})
    return record


@app.delete("/meetings/{session_id}")
async def delete_meeting(session_id: str):
    """Delete a saved meeting."""
    deleted = storage.delete_meeting(session_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Meeting not found"})
    return {"status": "deleted", "session_id": session_id}


@app.get("/debug/raw/{cycle}/{track}")
async def debug_raw(cycle: int, track: str):
    """Return raw Sonnet response saved to /tmp for a given cycle+track."""
    import pathlib
    path = pathlib.Path(f"/tmp/meeting_debug_cycle{cycle}_track{track}.txt")
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": f"No debug file at {path}"})
    return {"path": str(path), "content": path.read_text(encoding="utf-8")}


@app.get("/debug/list")
async def debug_list():
    """List all saved debug files in /tmp."""
    import pathlib, glob
    files = sorted(glob.glob("/tmp/meeting_debug_*.txt"))
    return {"files": files}


@app.post("/ask")
async def manual_ask(body: dict):
    """Manually inject a question for immediate recommendation."""
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "question is required"})

    ccm_event = await ccm_engine.process_transcript_segment(question + "?", is_final=True)
    if ccm_event:
        await handle_ccm_event(ccm_event)
    # Also feed into analysis engine
    await handle_final_transcript(question)

    return {"status": "queued", "question": question}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial state — may fail if React StrictMode cleanup already closed the socket
        try:
            await websocket.send_json({
                "type": "ccm_update",
                "ts": time.time(),
                "payload": ccm_engine.get_state_snapshot(),
            })
        except Exception as e:
            logger.debug(f"WS initial send failed (likely StrictMode first-mount cleanup): {e}")
            return  # finally block below will still call disconnect()

        while True:
            data = await websocket.receive_text()
            logger.debug(f"WS client message: {data[:100]}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error: {e}")
    finally:
        ws_manager.disconnect(websocket)
