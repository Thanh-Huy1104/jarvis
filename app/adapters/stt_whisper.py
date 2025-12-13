from __future__ import annotations
import os
import tempfile

from faster_whisper import WhisperModel

from app.domain.ports import STTPort
from app.core.config import settings


class FasterWhisperAdapter(STTPort):
    def __init__(self):
        self._model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")

    def transcribe(self, audio_bytes: bytes, *, filename: str | None = None) -> str:
        suffix = ""
        if filename and "." in filename:
            suffix = os.path.splitext(filename)[1]

        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as f:
            f.write(audio_bytes)
            f.flush()

            segments, _info = self._model.transcribe(f.name)
            text = "".join(seg.text for seg in segments).strip()

        return text
