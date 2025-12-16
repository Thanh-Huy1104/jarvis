"""Speed response node - fast path for simple queries"""

import logging
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage
from app.prompts.speed_response import get_speed_response_prompt

logger = logging.getLogger(__name__)


async def speed_response(engine, state) -> dict:
    """
    Node 2a: Fast path for simple queries (greetings, commands).
    Uses speed mode with low token limit.
    """
    logger.info("Taking SPEED path")
    
    # Retrieve memory context for conversation continuity
    ctx_data = engine.memory.get_context(
        query=state["user_input"], 
        user_id=state["user_id"]
    )
    
    # Format context
    history_str = "\n".join(f"- {h}" for h in ctx_data.get("relevant_history", []))
    context_str = f"RELEVANT PAST CONTEXT:\n{history_str}\n\n" if history_str else ""
    
    # Simple system prompt with memory context
    system_content = f"""You are Jarvis, a helpful AI assistant. Be concise and friendly.

{context_str}Respond naturally to the user's message."""
    
    system_msg = SystemMessage(content=system_content)
    user_msg = HumanMessage(content=state["user_input"])
    
    response = await engine.llm.run_agent_step(
        messages=[user_msg],
        system_persona=str(system_msg.content),
        tools=None,
        mode="speed"
    )
    
    return {
        "final_response": response.content,
        "messages": [user_msg, response]
    }


async def build_context(engine, state) -> dict:
    """
    Node 2b: Builds the Context Sandwich for complex queries.
    Retrieves from memory (vector + graph) and adds directives.
    """
    logger.info("Building context sandwich")
    
    ctx_data = engine.memory.get_context(
        query=state["user_input"], 
        user_id=state["user_id"]
    )
    
    # Format context as text
    history_str = "\n".join(f"- {h}" for h in ctx_data.get("relevant_history", []))
    context_str = f"RELEVANT PAST INTERACTIONS:\n{history_str}\n" if history_str else ""
    
    directives = ctx_data.get("user_directives", [])
    
    logger.debug(f"Context: {len(ctx_data.get('relevant_history', []))} memories, {len(directives)} directives")
    
    return {
        "memory_context": context_str,
        "global_directives": directives
    }
