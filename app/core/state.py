from __future__ import annotations
from typing import Dict, List
from app.core.types import ChatMessage


class InMemorySessionStore:
    def __init__(self):
        self._sessions: Dict[str, List[ChatMessage]] = {}

    def get_recent(self, session_id: str, limit: int) -> List[ChatMessage]:
        msgs = self._sessions.get(session_id, [])
        return msgs[-limit:]

    def append(self, session_id: str, msg: ChatMessage) -> None:
        self._sessions.setdefault(session_id, []).append(msg)
