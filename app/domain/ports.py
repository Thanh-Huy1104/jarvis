from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple

from app.core.types import ChatMessage, ToolDecision

class SessionStorePort(ABC):
    @abstractmethod
    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]: ...

    @abstractmethod
    def append(self, session_id: str, msg: ChatMessage) -> None: ...


class STTPort(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, *, filename: str | None = None) -> str: ...


class LLMPromptPort(ABC):
    @abstractmethod
    async def decide_next_step(
        self,
        *,
        user_text: str,
        history: List[Any], # Accepts List[ChatMessage] or List[Dict]
        tool_schemas: List[Dict[str, Any]],
        memories: List[str], # <--- NEW: Required for Memory Injection
    ) -> ToolDecision:
        """
        Analyzes context and decides the immediate next step (Tool or Chat).
        """
        ...

    @abstractmethod
    async def stream_response(
        self,
        *,
        user_text: str,
        history: List[Any],
        system_persona: str,
    ) -> AsyncIterable[str]: 
        """
        Streams the final verbal response. Context is now embedded in system_persona.
        """
        ...


class TTSPort(ABC):
    @abstractmethod
    def speak_wav(self, text: str) -> bytes: ...

    @abstractmethod
    def speak_pcm_f32(self, text: str) -> Tuple[bytes, int, int]:
        """Returns (pcm_f32le_bytes, sample_rate, channels)."""
        ...


class ToolsPort(ABC):
    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def call_tool(self, name: str, args: dict) -> str:
        ...


class MemoryPort(ABC):
    @abstractmethod
    def add(self, text: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> None: 
        """Add a memory/interaction to the long-term store."""
        ...

    @abstractmethod
    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]: 
        """Search for relevant memories."""
        ...