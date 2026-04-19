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

from backend.agentcore import client as agentcore_client
from backend.agentcore import memory as agentcore_memory
from backend.agent.recommendation_agent import RecommendationAgent
from backend.audio.capture import get_capture
from backend.ccm.engine import CCMEngine
from backend.config import settings
from backend.knowledge_base import bedrock_kb
from backend.websocket.manager import manager as ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

ccm_engine = CCMEngine()
event_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
recommendation_agent = RecommendationAgent(ws_manager, event_queue)

_meeting_task: asyncio.Task | None = None
_stop_event: asyncio.Event = asyncio.Event()
_session_id: str | None = None
_customer_id: str = "anonymous"
_customer_context: str = ""          # loaded from AgentCore Memory at session start

# Per-topic cooldown for AgentCore path (mirrors RecommendationAgent cooldown)
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
# AgentCore recommendation dispatcher (fires as background task)
# ---------------------------------------------------------------------------

async def _dispatch_recommendation(ccm_event) -> None:
    """Fire-and-forget: invoke AgentCore Runtime and broadcast the card."""
    ctx = ccm_event.context_snapshot
    topics = ctx.get("active_topics", [])
    topic_key = topics[0]["name"] if topics else "general"

    # Cooldown: don't spam the same topic
    if time.time() - _last_trigger.get(topic_key, 0) < COOLDOWN_SECONDS:
        return
    _last_trigger[topic_key] = time.time()

    # Build search query
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
    )

    if card and "error" not in card:
        await ws_manager.broadcast({
            "type": "recommendation",
            "ts": time.time(),
            "payload": card,
        })
        logger.info(f"AgentCore recommendation emitted: {card.get('title', '')}")

        # Save significant trigger to Memory for future sessions
        if _customer_id != "anonymous":
            await agentcore_memory.save_session_event(
                _customer_id,
                _session_id or "no-session",
                ccm_event.trigger_text,
                role="USER",
            )


async def handle_ccm_event(ccm_event) -> None:
    """Route a CCMUpdateEvent to AgentCore (preferred) or local agent (fallback)."""
    # Push CCM state to all WebSocket clients
    await ws_manager.broadcast({
        "type": "ccm_update",
        "ts": time.time(),
        "payload": ccm_event.context_snapshot,
    })

    if agentcore_client.is_configured():
        # AgentCore path: fire-and-forget background task
        asyncio.create_task(
            _dispatch_recommendation(ccm_event),
            name="agentcore-recommend",
        )
    else:
        # Local fallback: push to RecommendationAgent queue
        try:
            event_queue.put_nowait(ccm_event)
        except asyncio.QueueFull:
            try:
                event_queue.get_nowait()
                event_queue.put_nowait(ccm_event)
            except asyncio.QueueEmpty:
                pass


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Meeting Intelligence Assistant backend...")
    logger.info(f"STT provider: {settings.stt_provider}")

    if bedrock_kb.is_configured():
        logger.info(f"Bedrock KB: {settings.bedrock_kb_id} ({settings.bedrock_kb_search_type})")
    else:
        logger.warning(
            "BEDROCK_KB_ID not set — recommendations will be skipped. "
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
    version="0.2.0",
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
    }


@app.get("/meeting/state")
async def get_meeting_state():
    return ccm_engine.get_state_snapshot()


@app.post("/meeting/start")
async def start_meeting(
    customer_id: str = "anonymous",
    source: str = "auto",
    wav_path: str | None = None,
):
    global _meeting_task, _stop_event, _session_id, _customer_id, _customer_context, _last_trigger

    if _meeting_task and not _meeting_task.done():
        return JSONResponse(
            status_code=409,
            content={"error": "Meeting already in progress. Stop it first."},
        )

    ccm_engine.reset()
    _stop_event = asyncio.Event()
    _session_id = str(uuid.uuid4())
    _customer_id = customer_id.strip().lower() or "anonymous"
    _last_trigger = {}

    # Load prior customer context from AgentCore Memory
    _customer_context = await agentcore_memory.load_customer_context(_customer_id)
    if _customer_context:
        logger.info(f"Loaded prior context for customer '{_customer_id}'")

    capture = get_capture(wav_path)
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
        )

    _meeting_task = asyncio.create_task(run_pipeline(), name="meeting-pipeline")

    await ws_manager.broadcast({
        "type": "meeting_started",
        "ts": time.time(),
        "payload": {
            "session_id": _session_id,
            "customer_id": _customer_id,
            "stt_provider": settings.stt_provider,
            "customer_context_loaded": bool(_customer_context),
        },
    })

    logger.info(f"Meeting started. Session: {_session_id}, Customer: {_customer_id}")
    return {
        "session_id": _session_id,
        "customer_id": _customer_id,
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

    # Save session summary to AgentCore Memory
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
    ccm_engine.reset()
    return {"status": "reset", "session_id": ccm_engine.state.session_id}


@app.post("/ask")
async def manual_ask(body: dict):
    """Manually inject a question for immediate recommendation."""
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "question is required"})

    ccm_event = await ccm_engine.process_transcript_segment(question + "?", is_final=True)
    if ccm_event:
        await handle_ccm_event(ccm_event)

    return {"status": "queued", "question": question}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    await websocket.send_json({
        "type": "ccm_update",
        "ts": time.time(),
        "payload": ccm_engine.get_state_snapshot(),
    })
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WS client message: {data[:100]}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WS error: {e}")
        ws_manager.disconnect(websocket)
