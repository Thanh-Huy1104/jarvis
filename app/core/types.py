from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Simple Pydantic model for storage/API
class ChatMessage(BaseModel):
    role: str
    content: str

# We can keep these for explicit typing if needed elsewhere, 
# but the Graph mostly uses LangChain types (AIMessage, HumanMessage) internally.
class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any]
    id: Optional[str] = None