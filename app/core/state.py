from typing import Annotated, TypedDict, List, Dict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from app.core.types import ChatMessage
from app.domain.ports import SessionStorePort

class AgentState(TypedDict):
    """
    The state for the new ReAct Graph.
    
    We rely on 'messages' to hold the entire state (User inputs, AI thoughts, Tool outputs).
    The 'add_messages' reducer handles appending new messages automatically.
    """
    messages: Annotated[List[AnyMessage], add_messages]
    
    # Static context fields
    user_id: str
    user_input: str

class InMemorySessionStore(SessionStorePort):
    def __init__(self):
        self._sessions: Dict[str, List[ChatMessage]] = {}

    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]:
        msgs = self._sessions.get(session_id, [])
        return msgs[-limit:]

    def append(self, session_id: str, msg: ChatMessage) -> None:
        self._sessions.setdefault(session_id, []).append(msg)