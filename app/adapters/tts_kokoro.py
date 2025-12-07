from __future__ import annotations

import io
import threading
from typing import Tuple

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

from app.core.config import settings
from app.domain.ports import TTSPort


def _remove_dc(x: np.ndarray) -> np.ndarray:
    # Remove DC offset (prevents some “pop” cases)
    if x.size == 0:
        return x
    return (x - float(np.mean(x))).astype(np.float32, copy=False)


def _fade_in_out(
    x: np.ndarray,
    sr: int,
    fade_in_ms: float = 4.0,
    fade_out_ms: float = 28.0,
) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1).copy()
    n = x.shape[0]
    if n == 0:
        return x

    fi = int(sr * (fade_in_ms / 1000.0))
    fo = int(sr * (fade_out_ms / 1000.0))

    fi = min(fi, n)
    fo = min(fo, n)

    if fi >= 2:
        ramp = np.linspace(0.0, 1.0, fi, dtype=np.float32)
        x[:fi] *= ramp

    if fo >= 2:
        ramp = np.linspace(1.0, 0.0, fo, dtype=np.float32)
        x[-fo:] *= ramp

    return x


def _hard_gate_tail(x: np.ndarray, sr: int, gate_ms: float = 4.0) -> np.ndarray:
    # Ensure the last few ms are exactly zero (removes residual clicks)
    x = np.asarray(x, dtype=np.float32).reshape(-1).copy()
    n = x.shape[0]
    if n == 0:
        return x
    g = int(sr * (gate_ms / 1000.0))
    if g > 0:
        g = min(g, n)
        x[-g:] = 0.0
    return x


def _append_silence(x: np.ndarray, sr: int, tail_ms: float = 35.0) -> np.ndarray:
    tail = int(sr * (tail_ms / 1000.0))
    if tail <= 0:
        return x.astype(np.float32, copy=False)
    return np.concatenate([x.astype(np.float32, copy=False), np.zeros(tail, dtype=np.float32)], axis=0)


class KokoroAdapter(TTSPort):
    def __init__(self) -> None:
        self._tts = Kokoro(settings.kokoro_model, settings.kokoro_voices)
        self._lock = threading.Lock()

    def speak_wav(self, text: str) -> bytes:
        with self._lock:
            samples, sample_rate = self._tts.create(
                text,
                voice=settings.kokoro_voice_name,
                speed=settings.kokoro_speed,
                lang=settings.kokoro_lang,
            )

        buf = io.BytesIO()
        sf.write(buf, samples, int(sample_rate), format="WAV")
        return buf.getvalue()

    def speak_pcm_f32(self, text: str) -> Tuple[bytes, int, int]:
        with self._lock:
            samples, sample_rate = self._tts.create(
                text,
                voice=settings.kokoro_voice_name,
                speed=settings.kokoro_speed,
                lang=settings.kokoro_lang,
            )

        sr = int(sample_rate)
        arr = np.asarray(samples, dtype=np.float32).reshape(-1)

        # Strong boundary conditioning for chunked playback
        arr = _remove_dc(arr)
        arr = _fade_in_out(arr, sr, fade_in_ms=4.0, fade_out_ms=28.0)
        arr = _hard_gate_tail(arr, sr, gate_ms=4.0)
        arr = _append_silence(arr, sr, tail_ms=35.0)

        pcm_bytes = arr.astype("<f4", copy=False).tobytes()
        return pcm_bytes, sr, 1
