import logging
from langchain_core.messages import HumanMessage
from app.core.state import AgentState
from app.prompts.skill_documentation import get_skill_documentation_prompt

logger = logging.getLogger(__name__)

async def generate_skill_documentation(engine, state: AgentState) -> dict:
    """
    Node: Generates rich documentation (SKILL.md) for a verified skill.
    Uses the 'speed' model (or 'think' if complex) to synthesize the document.
    """
    logger.info("Generating rich skill documentation...")
    
    code = state.get("generated_code", "")
    description = state.get("user_input", "")
    # We might not have a name yet, or we can use the one proposed in propose_pending_skill if available.
    # But usually this runs after verification.
    
    if not code:
        logger.warning("No code available to document.")
        return {"skill_documentation": None}

    prompt = get_skill_documentation_prompt(code, description)
    
    try:
        response = await engine.llm.run_agent_step(
            messages=[HumanMessage(content=prompt)],
            system_persona="You are a technical documentation expert.",
            tools=None,
            mode="think" # Use think mode for higher quality docs
        )
        
        full_content = engine.llm.sanitize_thought_process(str(response.content))
        
        # Basic validation: Check for frontmatter
        if not full_content.strip().startswith("---"):
            logger.warning("Generated documentation missing frontmatter, attempting to fix...")
            # Fallback or wrap? For now just log.
            
        logger.info(f"Generated documentation ({len(full_content)} chars)")
        return {"skill_documentation": full_content}
        
    except Exception as e:
        logger.error(f"Failed to generate documentation: {e}")
        return {"skill_documentation": None}
