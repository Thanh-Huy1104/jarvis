from __future__ import annotations

import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

from app.core.config import settings
from app.domain.ports import TTSPort


def _remove_dc(x: np.ndarray) -> np.ndarray:
    if x.size == 0: return x
    return (x - float(np.mean(x))).astype(np.float32, copy=False)

def _fade_in_out(x: np.ndarray, sr: int, fade_ms: float = 4.0) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1).copy()
    n = x.shape[0]
    if n == 0: return x
    
    samples = int(sr * (fade_ms / 1000.0))
    samples = min(samples, n)
    
    if samples >= 2:
        ramp = np.linspace(0.0, 1.0, samples, dtype=np.float32)
        x[:samples] *= ramp
        x[-samples:] *= ramp[::-1]
    
    return x

class KokoroAdapter(TTSPort):
    def __init__(self) -> None:
        self._tts = Kokoro(settings.kokoro_model, settings.kokoro_voices)
        # Single worker pool to serialize requests
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._semaphore = asyncio.Semaphore(1)

    def _speak_pcm_f32_sync(self, text: str) -> Tuple[bytes, int, int]:
        """Synchronous TTS generation for thread pool execution."""
        samples, sample_rate = self._tts.create(
            text,
            voice=settings.kokoro_voice_name,
            speed=settings.kokoro_speed,
            lang=settings.kokoro_lang,
        )

        sr = int(sample_rate)
        arr = np.asarray(samples, dtype=np.float32).reshape(-1)

        arr = _remove_dc(arr)
        arr = _fade_in_out(arr, sr, fade_ms=5.0)

        pcm_bytes = arr.tobytes()
        return pcm_bytes, sr, 1

    def speak_wav(self, text: str) -> bytes:
        """Legacy sync interface - runs in thread pool."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.speak_wav_async(text))
        finally:
            loop.close()

    async def speak_wav_async(self, text: str) -> bytes:
        """Async WAV generation with request queuing."""
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            samples, sample_rate = await loop.run_in_executor(
                self._executor,
                lambda: self._tts.create(
                    text,
                    voice=settings.kokoro_voice_name,
                    speed=settings.kokoro_speed,
                    lang=settings.kokoro_lang,
                )
            )
        buf = io.BytesIO()
        sf.write(buf, samples, int(sample_rate), format="WAV")
        return buf.getvalue()

    def speak_pcm_f32(self, text: str) -> Tuple[bytes, int, int]:
        """Legacy sync interface - runs in thread pool."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.speak_pcm_f32_async(text))
        finally:
            loop.close()

    async def speak_pcm_f32_async(self, text: str) -> Tuple[bytes, int, int]:
        """Async PCM generation with request queuing."""
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                self._speak_pcm_f32_sync,
                text
            )