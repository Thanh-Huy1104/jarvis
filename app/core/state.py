from __future__ import annotations
from typing import Dict, List
from app.core.types import ChatMessage
import operator
from typing import Annotated, TypedDict, List, Optional, Any, Dict
from pydantic import BaseModel

class InMemorySessionStore:
    def __init__(self):
        self._sessions: Dict[str, List[ChatMessage]] = {}

    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]:
        msgs = self._sessions.get(session_id, [])
        return msgs[-limit:]

    def append(self, session_id: str, msg: ChatMessage) -> None:
        self._sessions.setdefault(session_id, []).append(msg)

class AgentMessage(BaseModel):
    role: str
    content: str

class AgentState(TypedDict):
    # 'operator.add' tells LangGraph to APPEND new messages to this list
    # instead of overwriting the whole list every step.
    messages: Annotated[List[AgentMessage], operator.add]
    
    # Context
    user_input: str
    user_id: str
    relevant_memories: List[str]
    
    # Internal Scratchpad (Planner -> Tool -> Responder flow)
    next_step: Optional[str]        # "tool" or "respond"
    current_thought: Optional[str]  # The reasoning text
    tool_call: Optional[Dict[str, Any]] 
    assistant_hint: Optional[str]   # Data passed to the voice generator
    
    loop_step: Annotated[int, operator.add] # Tracks recursion depth