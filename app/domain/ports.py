from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncIterable, Optional
from langchain_core.messages import BaseMessage, AIMessage
from app.core.types import ChatMessage

class SessionStorePort(ABC):
    @abstractmethod
    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]: ...
    
    @abstractmethod
    def append(self, session_id: str, msg: ChatMessage) -> None: ...

class STTPort(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, filename: str | None = None) -> str: 
        """Synchronous transcription (legacy)."""
        ...
    
    @abstractmethod
    async def transcribe_async(self, audio_bytes: bytes, filename: str | None = None) -> str: 
        """Async transcription with request queuing."""
        ...

class TTSPort(ABC):
    @abstractmethod
    def speak_pcm_f32(self, text: str) -> tuple[bytes, int, int]: 
        """Synchronous TTS (legacy)."""
        ...
    
    @abstractmethod
    async def speak_pcm_f32_async(self, text: str) -> tuple[bytes, int, int]: 
        """Async TTS with request queuing."""
        ...

class MemoryPort(ABC):
    @abstractmethod
    async def add(self, text: str, user_id: str) -> None: ...
    
    @abstractmethod
    async def search(self, query: str, user_id: str, limit: int = 5) -> List[str]: ...

class LLMPromptPort(ABC):
    @abstractmethod
    async def run_agent_step(
        self, 
        messages: List[BaseMessage], 
        system_persona: str, 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AIMessage:
        """
        Executes a single step of the agent. 
        Returns a LangChain AIMessage (which may contain text or tool_calls).
        """
        ...
    @abstractmethod
    async def summarize(
        self,
        user_message: str,
        assistant_message: str
        ) -> str:
        ...