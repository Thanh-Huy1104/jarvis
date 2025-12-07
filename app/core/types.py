from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolDecision(BaseModel):
    intent: Literal["tool", "chat"] = "chat"
    tool_calls: List[ToolCall] = Field(default_factory=list)
    assistant_hint: Optional[str] = None


class ToolResult(BaseModel):
    name: str
    ok: bool
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class TurnResult(BaseModel):
    user_text: str
    assistant_text: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    audio_wav_bytes: bytes
