"""Local Whisper STT pipeline using faster-whisper.

Uses whisper-large-v3-turbo (or configurable model) for on-device transcription.
Ideal for MacBook deployments where privacy matters or Transcribe is unavailable.

Audio is buffered in a sliding window and transcribed every BUFFER_SECONDS.
Results are emitted in the same WebSocket message format as transcribe_stream.py.

Install the extra dependency:
    uv sync --extra whisper
    # or: uv add faster-whisper
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from backend.config import settings

if TYPE_CHECKING:
    from backend.ccm.engine import CCMEngine
    from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

_model = None  # lazy-loaded singleton


def _get_model():
    """Lazy-load the Whisper model on first use (avoids startup delay)."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed.\n"
                "Run: uv add faster-whisper\n"
                "Or: uv sync --extra whisper"
            )
        logger.info(
            f"Loading Whisper model '{settings.whisper_model}' "
            f"on device='{settings.whisper_device}' "
            f"compute_type='{settings.whisper_compute_type}'..."
        )
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper model loaded.")
    return _model


def _transcribe_chunk(audio_bytes: bytes, language: str) -> str:
    """Run Whisper transcription on a raw PCM bytes buffer.

    audio_bytes: 16-bit signed int, 16kHz, mono
    Returns: transcribed text string
    """
    model = _get_model()

    # Convert int16 PCM bytes → float32 numpy array normalised to [-1, 1]
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # Silence detection: skip if RMS is below threshold (no speech)
    rms = np.sqrt(np.mean(audio_np ** 2))
    if rms < 0.005:
        return ""

    segments, _ = model.transcribe(
        audio_np,
        language=language,
        beam_size=5,
        vad_filter=True,           # skip non-speech segments
        vad_parameters={"min_silence_duration_ms": 500},
    )
    return " ".join(seg.text for seg in segments).strip()


async def stream_transcription(
    audio_gen,
    ccm_engine: "CCMEngine",
    ws_manager: "ConnectionManager",
    event_queue: asyncio.Queue,
    stop_event: asyncio.Event,
    on_ccm_event=None,
    on_final_transcript=None,
) -> None:
    """Whisper-based transcription pipeline.

    Buffers WHISPER_BUFFER_SECONDS of audio, then transcribes synchronously
    (in a thread executor to avoid blocking the event loop).
    Emits final transcript segments — no partial results (Whisper limitation).
    """
    sample_rate = settings.audio_sample_rate
    buffer_samples = int(settings.whisper_buffer_seconds * sample_rate)
    overlap_samples = int(0.5 * sample_rate)  # 0.5s overlap to avoid cutting words
    bytes_per_sample = 2  # 16-bit

    buffer = bytearray()
    loop = asyncio.get_event_loop()

    logger.info(
        f"Whisper STT started. Model: {settings.whisper_model}, "
        f"buffer: {settings.whisper_buffer_seconds}s"
    )

    try:
        async for chunk in audio_gen:
            if stop_event.is_set():
                break

            buffer.extend(chunk)

            # Process when buffer is full
            if len(buffer) >= buffer_samples * bytes_per_sample:
                audio_to_transcribe = bytes(buffer[: buffer_samples * bytes_per_sample])

                # Run blocking transcription in executor
                text = await loop.run_in_executor(
                    None,
                    _transcribe_chunk,
                    audio_to_transcribe,
                    settings.whisper_language,
                )

                if text:
                    logger.debug(f"Whisper: {text[:80]}")

                    # Broadcast as final transcript (Whisper has no partials)
                    await ws_manager.broadcast({
                        "type": "transcript_final",
                        "ts": time.time(),
                        "payload": {
                            "text": text,
                            "speaker": None,  # Whisper has no speaker diarization in this mode
                            "is_partial": False,
                        },
                    })

                    # Feed AnalysisEngine cadence (every final segment)
                    if on_final_transcript:
                        await on_final_transcript(text)

                    # Update CCM
                    ccm_event = await ccm_engine.process_transcript_segment(text, is_final=True)
                    if ccm_event:
                        if on_ccm_event:
                            await on_ccm_event(ccm_event)
                        else:
                            try:
                                event_queue.put_nowait(ccm_event)
                            except asyncio.QueueFull:
                                try:
                                    event_queue.get_nowait()
                                    event_queue.put_nowait(ccm_event)
                                except asyncio.QueueEmpty:
                                    pass

                # Keep overlap window to avoid cutting words at buffer boundary
                buffer = buffer[
                    (buffer_samples - overlap_samples) * bytes_per_sample:
                ]

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Whisper stream error: {e}", exc_info=True)
        await ws_manager.broadcast({
            "type": "error",
            "ts": time.time(),
            "payload": {"message": f"Whisper transcription error: {e}"},
        })
    finally:
        logger.info("Whisper STT stopped.")
