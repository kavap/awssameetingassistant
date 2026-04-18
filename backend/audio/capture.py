"""Audio capture: microphone (sounddevice) and file-based fake capture.

The async generator yields raw PCM bytes (16-bit, 16kHz, mono) in 100ms chunks.
FakeAudioCapture reads a WAV file and emits chunks at the same rate for testing
in headless/cloud environments with no physical audio device.
"""
from __future__ import annotations

import asyncio
import wave
from pathlib import Path
from typing import AsyncGenerator

from backend.config import settings

# Bytes per 100ms chunk: 16000 samples/s * 0.1s * 2 bytes/sample * 1 channel
_CHUNK_BYTES = int(settings.audio_sample_rate * settings.audio_chunk_duration_ms / 1000 * 2)


class MicCapture:
    """Capture audio from the default system microphone."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        """sounddevice callback — runs in a separate thread."""
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(self._queue.put_nowait, bytes(indata))

    async def audio_generator(self) -> AsyncGenerator[bytes, None]:
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError(
                "sounddevice is not installed. Run: uv add sounddevice"
            )

        self._stream = sd.RawInputStream(
            samplerate=settings.audio_sample_rate,
            channels=1,
            dtype="int16",
            blocksize=int(settings.audio_sample_rate * settings.audio_chunk_duration_ms / 1000),
            callback=self._callback,
        )
        with self._stream:
            while True:
                chunk = await self._queue.get()
                if chunk is None:
                    break
                yield chunk

    def stop(self) -> None:
        self._queue.put_nowait(None)


class FakeAudioCapture:
    """Emit audio chunks from a WAV file for testing without a microphone.

    Respects real-time pacing — emits one chunk every AUDIO_CHUNK_DURATION_MS.
    If file is too short, loops back to the beginning.
    """

    def __init__(self, wav_path: str | None = None) -> None:
        self._path = wav_path or settings.fake_audio_path
        self._stop = False

    async def audio_generator(self) -> AsyncGenerator[bytes, None]:
        path = Path(self._path)
        if not path.exists():
            raise FileNotFoundError(
                f"Fake audio file not found: {self._path}. "
                "Provide a WAV file or set USE_FAKE_AUDIO=false."
            )

        delay = settings.audio_chunk_duration_ms / 1000.0  # seconds

        while not self._stop:
            with wave.open(str(path), "rb") as wf:
                while not self._stop:
                    raw = wf.readframes(
                        int(settings.audio_sample_rate * settings.audio_chunk_duration_ms / 1000)
                    )
                    if not raw:
                        break  # loop file
                    # Pad or trim to exact chunk size
                    if len(raw) < _CHUNK_BYTES:
                        raw = raw + b"\x00" * (_CHUNK_BYTES - len(raw))
                    yield raw[:_CHUNK_BYTES]
                    await asyncio.sleep(delay)

    def stop(self) -> None:
        self._stop = True


class SilenceCapture:
    """Emit silence chunks — useful when no audio source is available.

    This prevents the backend from crashing in environments with no audio.
    The transcription pipeline will simply produce no transcript.
    """

    def __init__(self) -> None:
        self._stop = False

    async def audio_generator(self) -> AsyncGenerator[bytes, None]:
        delay = settings.audio_chunk_duration_ms / 1000.0
        silence = b"\x00" * _CHUNK_BYTES
        while not self._stop:
            yield silence
            await asyncio.sleep(delay)

    def stop(self) -> None:
        self._stop = True


def get_capture(wav_path: str | None = None):
    """Factory: return the appropriate capture object based on config."""
    if settings.use_fake_audio:
        path = wav_path or settings.fake_audio_path
        if Path(path).exists():
            return FakeAudioCapture(path)
        return SilenceCapture()
    try:
        import sounddevice as sd
        sd.query_devices(kind="input")
        return MicCapture()
    except Exception:
        return SilenceCapture()
