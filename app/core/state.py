from typing import Annotated, TypedDict, List, Dict, Optional
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from app.core.types import ChatMessage
from app.domain.ports import SessionStorePort


class SubTask(TypedDict):
    """Represents a subtask in a complex plan"""
    id: str
    description: str
    status: str  # "pending", "complete", "failed"
    result: Optional[str]


class AgentState(TypedDict):
    """
    Enhanced state for the code-first Jarvis engine.
    Supports both speed mode (chat) and complex mode (planning + code execution).
    """
    # Legacy message-based state (for backward compatibility)
    messages: Annotated[List[AnyMessage], add_messages]
    
    # Core Inputs
    user_input: str
    user_id: str
    
    # Classification
    intent_mode: str  # "speed" or "complex"
    
    # Context (The Sandwich)
    memory_context: str
    global_directives: Annotated[List[str], operator.add]
    
    # Planning (for complex tasks)
    plan: Annotated[List[SubTask], operator.add]
    
    # Code Execution
    generated_code: str
    execution_result: str
    
    # Skill Management
    pending_skill_name: str
    skill_approved: bool
    existing_skill_code: Optional[str]  # For deduplication
    used_skill_names: Annotated[List[str], operator.add]  # Track skills used in this request
    
    # Final Output
    final_response: str

class InMemorySessionStore(SessionStorePort):
    def __init__(self):
        self._sessions: Dict[str, List[ChatMessage]] = {}

    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]:
        msgs = self._sessions.get(session_id, [])
        return msgs[-limit:]

    def append(self, session_id: str, msg: ChatMessage) -> None:
        self._sessions.setdefault(session_id, []).append(msg)