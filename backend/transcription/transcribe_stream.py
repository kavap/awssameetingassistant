"""Amazon Transcribe Streaming pipeline.

Uses the amazon-transcribe SDK (HTTP/2 bidirectional stream).
Feeds the CCM engine and broadcasts over WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from backend.ccm.engine import CCMEngine
from backend.config import settings

if TYPE_CHECKING:
    from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


async def _send_audio(stream, audio_gen):
    """Producer: send audio chunks into the Transcribe input stream."""
    try:
        async for chunk in audio_gen:
            await stream.input_stream.send_audio_event(audio_chunk=chunk)
        await stream.input_stream.end_stream()
    except Exception as e:
        logger.error(f"Audio send error: {e}")
        await stream.input_stream.end_stream()


async def _receive_transcripts(stream, ccm_engine: CCMEngine, ws_manager, event_queue: asyncio.Queue):
    """Consumer: receive Transcribe events, update CCM, push to WebSocket."""
    try:
        async for event in stream.output_stream:
            if hasattr(event, "transcript"):
                transcript = event.transcript
                for result in transcript.results:
                    if not result.alternatives:
                        continue
                    text = result.alternatives[0].transcript.strip()
                    if not text:
                        continue

                    is_partial = result.is_partial
                    speaker = None

                    # Speaker diarization: extract from first item if available
                    if result.alternatives[0].items:
                        first_item = result.alternatives[0].items[0]
                        if hasattr(first_item, "speaker") and first_item.speaker:
                            speaker = first_item.speaker

                    msg_type = "transcript_partial" if is_partial else "transcript_final"
                    await ws_manager.broadcast({
                        "type": msg_type,
                        "ts": time.time(),
                        "payload": {
                            "text": text,
                            "speaker": speaker,
                            "is_partial": is_partial,
                        },
                    })

                    if not is_partial:
                        ccm_event = ccm_engine.process_transcript_segment(text, is_final=True)
                        if ccm_event:
                            # Push CCM state update to WebSocket
                            await ws_manager.broadcast({
                                "type": "ccm_update",
                                "ts": time.time(),
                                "payload": ccm_event.context_snapshot,
                            })
                            # Enqueue for recommendation agent (non-blocking)
                            try:
                                event_queue.put_nowait(ccm_event)
                            except asyncio.QueueFull:
                                # Drop oldest event to make room
                                try:
                                    event_queue.get_nowait()
                                    event_queue.put_nowait(ccm_event)
                                except asyncio.QueueEmpty:
                                    pass
                    else:
                        # Process partial for service detection only (no transcript append)
                        ccm_engine.process_transcript_segment(text, is_final=False)

    except Exception as e:
        logger.error(f"Transcript receive error: {e}")


async def stream_transcription(
    audio_gen,
    ccm_engine: CCMEngine,
    ws_manager,
    event_queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> None:
    """Main transcription loop with retry logic."""
    attempt = 0

    while attempt < MAX_RETRIES and not stop_event.is_set():
        try:
            from amazon_transcribe.client import TranscribeStreamingClient

            client = TranscribeStreamingClient(region=settings.transcribe_region)

            stream = await client.start_stream_transcription(
                language_code=settings.transcribe_language,
                media_sample_rate_hz=settings.audio_sample_rate,
                media_encoding="pcm",
                enable_partial_results_stabilization=True,
                partial_results_stability="high",
                show_speaker_label=True,
            )

            logger.info("Transcribe stream started.")
            attempt = 0  # reset on successful connection

            await asyncio.gather(
                _send_audio(stream, audio_gen),
                _receive_transcripts(stream, ccm_engine, ws_manager, event_queue),
            )
            break  # clean exit

        except stop_event.__class__:
            break
        except Exception as e:
            attempt += 1
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"Transcribe error (attempt {attempt}/{MAX_RETRIES}): {e}. Retrying in {wait}s...")
            if attempt < MAX_RETRIES and not stop_event.is_set():
                await asyncio.sleep(wait)
            else:
                logger.error("Max retries reached. Transcription stopped.")
                await ws_manager.broadcast({
                    "type": "error",
                    "ts": time.time(),
                    "payload": {"message": f"Transcription failed: {e}"},
                })
