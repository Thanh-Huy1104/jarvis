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
    def transcribe(self, audio_bytes: bytes, filename: str | None = None) -> str: ...

class TTSPort(ABC):
    @abstractmethod
    def speak_pcm_f32(self, text: str) -> tuple[bytes, int, int]: ...

class ToolsPort(ABC):
    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    async def call_tool(self, name: str, args: dict) -> str: ...
    
    async def connect(self) -> None:
        """Optional: Connect to tool provider (e.g., MCP server)"""
        pass
    
    async def cleanup(self) -> None:
        """Optional: Cleanup tool provider resources"""
        pass

class MemoryPort(ABC):
    @abstractmethod
    def add(self, text: str, user_id: str) -> None: ...
    
    @abstractmethod
    def search(self, query: str, user_id: str, limit: int = 5) -> List[str]: ...

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
    async def stream_response(
        self,
        *,
        history: List[BaseMessage],
        system_persona: str,
    ) -> AsyncIterable[str]:
        """
        Used for streaming the final text response if needed.
        """
        ...