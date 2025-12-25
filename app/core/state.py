from typing import Annotated, TypedDict, List, Dict, Optional
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from app.core.types import ChatMessage


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
    
    Note: 'messages' are persisted automatically by the LangGraph checkpointer.
    Do not manually append history to input; use add_messages reducer.
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
    global_directives: List[str]
    
    # Planning (for complex tasks)
    plan: List[SubTask]
    
    # Code Execution
    generated_code: str
    execution_result: str
    execution_error: Optional[str]  # Error traceback for self-correction
    retry_count: int  # Number of self-correction attempts
    
    # Linting and Testing
    lint_error: Optional[str]
    test_output: Optional[str]
    
    # Skill Management
    pending_skill_name: str
    existing_skill_code: Optional[str]  # For deduplication
    used_skill_names: List[str]  # Track skills used in this request
    
    # Final Output
    final_response: str
    
    