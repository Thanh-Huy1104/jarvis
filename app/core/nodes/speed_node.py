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
    ctx_data = await engine.memory.get_context(
        query=state["user_input"], 
        user_id=state["user_id"]
    )
    
    # Format context (Long-term memory)
    history_str = "\n".join(f"- {h}" for h in ctx_data.get("relevant_history", []))
    
    # Add recent memories (summarized context)
    recent_memories = ctx_data.get("recent_history", [])
    recent_memories_str = "\n".join(f"- {h}" for h in recent_memories)
    
    context_str = ""
    if history_str:
        context_str += f"RELEVANT PAST CONTEXT:\n{history_str}\n\n"
    if recent_memories_str:
        context_str += f"RECENT MEMORIES:\n{recent_memories_str}\n\n"
    
    # Simple system prompt with memory context
    system_content = f"""You are Jarvis, a helpful AI assistant. Be concise and friendly.

{context_str}Respond naturally to the user's message."""
    
    system_msg = SystemMessage(content=system_content)
    user_msg = HumanMessage(content=state["user_input"])
    
    # robust short-term memory: Pass actual message objects
    # This preserves the chat structure (User -> AI -> User) better than text injection
    messages = state.get("messages", [])
    logger.info(f"DEBUG: State has {len(messages)} messages")
    
    recent_messages = messages[-6:] if messages else []
    
    # Combine history + current input
    input_messages = recent_messages + [user_msg]
    
    logger.info(f"DEBUG: Sending {len(input_messages)} messages to LLM")
    for idx, m in enumerate(input_messages):
        logger.info(f"DEBUG Msg {idx} ({m.type}): {str(m.content)[:50]}...")
    
    response = await engine.llm.run_agent_step(
        messages=input_messages,
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
    Also includes recent conversation history for continuity.
    """
    logger.info("Building context sandwich")
    
    ctx_data = await engine.memory.get_context(
        query=state["user_input"], 
        user_id=state["user_id"]
    )
    
    # Format relevant history (vector search results)
    history_str = "\n".join(f"- {h}" for h in ctx_data.get("relevant_history", []))
    
    # Get recent conversation history for continuity
    recent_history = ctx_data.get("recent_history", [])
    recent_str = ""
    if recent_history:
        recent_str = "RECENT CONVERSATION:\n" + "\n".join(f"- {h}" for h in recent_history[-5:]) + "\n\n"
    
    # Combine contexts
    context_str = ""
    if recent_str:
        context_str += recent_str
    if history_str:
        context_str += f"RELEVANT PAST CONTEXT:\n{history_str}\n"
    
    directives = ctx_data.get("user_directives", [])
    
    logger.debug(f"Context: {len(recent_history)} recent, {len(ctx_data.get('relevant_history', []))} relevant memories, {len(directives)} directives")
    
    return {
        "memory_context": context_str,
        "global_directives": directives
    }
