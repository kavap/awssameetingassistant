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


# ---------------------------------------------------------------------------
# STT provider selection
# ---------------------------------------------------------------------------

def _get_stream_transcription_fn():
    """Return the correct STT stream function based on STT_PROVIDER config."""
    provider = settings.stt_provider.lower()
    if provider == "whisper":
        logger.info("STT provider: faster-whisper (local)")
        from backend.transcription.whisper_stream import (
            stream_transcription as whisper_fn,
        )
        return whisper_fn
    else:
        logger.info("STT provider: Amazon Transcribe Streaming (cloud)")
        from backend.transcription.transcribe_stream import (
            stream_transcription as transcribe_fn,
        )
        return transcribe_fn


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Meeting Intelligence Assistant backend...")
    logger.info(f"STT provider: {settings.stt_provider}")

    if bedrock_kb.is_configured():
        logger.info(f"Bedrock KB: {settings.bedrock_kb_id} ({settings.bedrock_kb_search_type} search)")
    else:
        logger.warning(
            "BEDROCK_KB_ID not set — recommendations will be skipped. "
            "Run scripts/setup_kb.py or create a KB in the AWS console, "
            "then set BEDROCK_KB_ID in .env."
        )

    recommendation_agent.start()
    yield
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
    version="0.1.0",
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
        "ws_clients": ws_manager.connection_count,
        "session_id": _session_id,
    }


@app.get("/meeting/state")
async def get_meeting_state():
    return ccm_engine.get_state_snapshot()


@app.post("/meeting/start")
async def start_meeting(source: str = "auto", wav_path: str | None = None):
    global _meeting_task, _stop_event, _session_id

    if _meeting_task and not _meeting_task.done():
        return JSONResponse(
            status_code=409,
            content={"error": "Meeting already in progress. Stop it first."},
        )

    ccm_engine.reset()
    _stop_event = asyncio.Event()
    _session_id = str(uuid.uuid4())

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
        )

    _meeting_task = asyncio.create_task(run_pipeline(), name="meeting-pipeline")

    await ws_manager.broadcast({
        "type": "meeting_started",
        "ts": time.time(),
        "payload": {"session_id": _session_id, "stt_provider": settings.stt_provider},
    })

    logger.info(f"Meeting started. Session: {_session_id}, STT: {settings.stt_provider}")
    return {"session_id": _session_id, "status": "started", "stt_provider": settings.stt_provider}


@app.post("/meeting/stop")
async def stop_meeting():
    global _meeting_task, _stop_event, _session_id

    _stop_event.set()
    if _meeting_task and not _meeting_task.done():
        _meeting_task.cancel()

    await ws_manager.broadcast({
        "type": "meeting_stopped",
        "ts": time.time(),
        "payload": {"session_id": _session_id},
    })

    logger.info(f"Meeting stopped. Session: {_session_id}")
    _session_id = None
    return {"status": "stopped"}


@app.post("/meeting/reset")
async def reset_meeting():
    ccm_engine.reset()
    return {"status": "reset", "session_id": ccm_engine.state.session_id}


@app.post("/ask")
async def manual_ask(body: dict):
    """Manually inject a question into the CCM for immediate recommendation."""
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "question is required"})

    ccm_event = ccm_engine.process_transcript_segment(question + "?", is_final=True)
    if ccm_event:
        try:
            event_queue.put_nowait(ccm_event)
        except asyncio.QueueFull:
            pass

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
