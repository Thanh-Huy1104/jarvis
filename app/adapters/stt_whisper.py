from __future__ import annotations
import os
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel

from app.domain.ports import STTPort
from app.core.config import settings


class FasterWhisperAdapter(STTPort):
    def __init__(self):
        self._model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        # Single worker pool to serialize requests
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._semaphore = asyncio.Semaphore(1)

    def _transcribe_sync(self, audio_bytes: bytes, filename: str | None = None) -> str:
        """Synchronous transcription method for thread pool execution."""
        suffix = ""
        if filename and "." in filename:
            suffix = os.path.splitext(filename)[1]

        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as f:
            f.write(audio_bytes)
            f.flush()

            segments, _info = self._model.transcribe(f.name)
            text = "".join(seg.text for seg in segments).strip()

        return text

    def transcribe(self, audio_bytes: bytes, *, filename: str | None = None) -> str:
        """Legacy sync interface - runs in thread pool."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.transcribe_async(audio_bytes, filename=filename))
        finally:
            loop.close()

    async def transcribe_async(self, audio_bytes: bytes, *, filename: str | None = None) -> str:
        """Async transcription with request queuing."""
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor, 
                self._transcribe_sync, 
                audio_bytes, 
                filename
            )
