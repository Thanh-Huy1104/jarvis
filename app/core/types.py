from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Simple Pydantic model for storage/API
class ChatMessage(BaseModel):
    id: Optional[int] = None
    role: str
    content: str
    created_at: Optional[datetime] = None

# We can keep these for explicit typing if needed elsewhere, 
# but the Graph mostly uses LangChain types (AIMessage, HumanMessage) internally.
class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any]
    id: Optional[str] = None