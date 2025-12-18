"""Complex reasoning and code execution nodes"""

import logging
import time
import datetime # Import datetime
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.utils.code_extraction import extract_code
from app.core.utils.code_transform import ensure_print_output
from app.prompts.code_generation import get_code_generation_prompt
from app.prompts.synthesis import get_synthesis_prompt

logger = logging.getLogger(__name__)


async def reason_and_code(engine, state) -> dict:
    """
    Node 3: Thinking mode - LLM plans and generates Python code.
    Checks skill library for relevant snippets first (supports multi-skill combination).
    Supports self-correction: if retry_count > 0, includes error feedback in context.
    """
    start_time = time.time()
    retry_count = state.get("retry_count", 0)
    
    if retry_count > 0:
        logger.info(f"🔄 SELF-CORRECTION mode - Retry attempt {retry_count}")
    else:
        logger.info("Entering THINK mode - generating code")
    
    # Search for multiple relevant skills (top 3)
    relevant_skills = engine.skills.find_top_skills(state["user_input"], n=3, threshold=1.2)
    
    # Build skills section for prompt
    if relevant_skills:
        logger.info(f"Found {len(relevant_skills)} relevant skills: ")
        skill_names = []
        for skill in relevant_skills:
            logger.info(f"- {skill['name']}")
            skill_names.append(skill['name'])
        
        skills_section = "\n\nRELEVANT SKILLS FROM LIBRARY (combine/modify as needed):\n"
        for i, skill in enumerate(relevant_skills, 1):
            skills_section += f"\n--- Skill {i}: {skill['name']} (similarity: {1 - float(skill['distance']):.2f}) ---\n"
            skills_section += f"```python\n{skill['code']}\n```\n"
        
        # Store first skill code and all skill names for deduplication
        existing_skill_code = relevant_skills[0]['code']
        used_skill_names = skill_names
    else:
        skills_section = ""
        existing_skill_code = None
        used_skill_names = []
        logger.info("No relevant skills found in library")
    
    # Format message history for context
    messages = state.get("messages", [])
    message_context = ""
    if messages:
        recent_messages = messages[-6:]  # Last 6 messages (3 exchanges)
        formatted = []
        for msg in recent_messages:
            role = "User" if msg.type == "human" else "Assistant"
            content = str(msg.content)[:500]  # Increased to capture full errors
            formatted.append(f"{role}: {content}")
        message_context = "\n\nRECENT CONVERSATION:\n" + "\n".join(formatted) + "\n"
        
        # If this is a retry, emphasize the error context
        if retry_count > 0:
            message_context += "\n⚠️ IMPORTANT: The previous code attempt failed. Please analyze the error above and fix the issues.\n"
    
    # Get current date
    current_date = datetime.date.today().strftime("%B %d, %Y")
    
    # Build enhanced prompt using template
    memory_with_history = state.get('memory_context', '') + message_context
    
    prompt = get_code_generation_prompt(
        user_input=state['user_input'],
        memory_context=memory_with_history,
        directives=state.get("global_directives", []),
        skills_section=skills_section,
        current_date=current_date # Pass current date to the prompt
    )
    
    # Log context for debugging
    memory_ctx = state.get('memory_context', '')
    if memory_ctx:
        logger.info(f"Memory context included ({len(memory_ctx)} chars):")
        logger.info(f"{memory_ctx[:500]}...")
    else:
        logger.warning("No memory context in state!")
    
    logger.debug(f"Full prompt length: {len(prompt)} chars")
    
    system_msg = SystemMessage(content="You are Jarvis, an expert AI assistant with a Python sandbox. You have access to web search (duckduckgo-search), web scraping (requests + BeautifulSoup), data analysis (pandas, numpy). Write clear, working Python code to accomplish tasks.")
    user_msg = HumanMessage(content=prompt)
    
    response = await engine.llm.run_agent_step(
        messages=[user_msg],
        system_persona=str(system_msg.content),
        tools=None,
        mode="think"
    )
    
    # Sanitize thinking process (remove <think> tags if present)
    clean_content = engine.llm.sanitize_thought_process(str(response.content))
    
    # Extract Python code block
    code = extract_code(clean_content, engine.llm)
    
    logger.info(f"Generated code: {len(code)} characters")
    
    elapsed = (time.time() - start_time) * 1000
    engine._timing['reason_and_code'] = elapsed
    logger.info(f"⏱️  reason_and_code: {elapsed:.1f}ms")
    
    return {
        "generated_code": code,
        "final_response": clean_content,
        "messages": [user_msg, AIMessage(content=clean_content)],
        "existing_skill_code": existing_skill_code,
        "used_skill_names": used_skill_names
    }


async def execute_code(engine, state) -> dict:
    """
    Node 4: Executes generated Python code in Docker sandbox.
    Implements self-correction: on error, adds traceback to messages and routes back to think_agent.
    """
    start_time = time.time()
    code = state.get("generated_code", "")
    retry_count = state.get("retry_count", 0)
    
    if not code:
        logger.info("No code to execute")
        return {
            "execution_result": "No code was generated.",
            "execution_error": None,
            "retry_count": retry_count
        }
    
    # # Auto-inject prints if code doesn't have them
    # code = ensure_print_output(code)
    
    logger.info(f"Executing code in sandbox ({len(code)} chars) - Attempt {retry_count + 1}")
    
    result = engine.sandbox.execute_with_packages(code)
    
    logger.info(f"Execution result: {result[:100]}...")
    
    # Check for execution errors (detect common error patterns)
    error_indicators = ["Error:", "Traceback", "Exception:", "SyntaxError", "ImportError", "AttributeError", "KeyError", "ValueError", "TypeError"]
    has_error = any(indicator in result for indicator in error_indicators)
    
    if has_error:
        logger.warning(f"⚠️ Execution error detected - initiating self-correction loop")
        
        # Add error feedback to messages for next iteration
        error_msg = AIMessage(content=f"Previous code execution failed with error:\n\n```\n{result}\n```\n\nPlease analyze the error and generate corrected code.")
        
        return {
            "execution_result": result,
            "execution_error": result,  # Store error for routing logic
            "retry_count": retry_count + 1,
            "messages": [error_msg],  # Add error feedback to conversation
            "generated_code": code,
            "existing_skill_code": state.get("existing_skill_code"),
            "used_skill_names": state.get("used_skill_names", []),
            "skill_approved": False
        }
    
    # Success path: synthesize response
    logger.info("✅ Execution succeeded")
    
    # Strip base64 data from result for LLM synthesis (too large for context)
    # Clean up "Plot saved to..." messages from output to prevent LLM hallucinations
    result_for_llm = result # No plots to remove
    
    # Use SPEED LLM to synthesize a natural response from raw execution output
    synthesis_prompt = get_synthesis_prompt(state['user_input'], result_for_llm)
    
    try:
        synthesis_response = await engine.llm.run_agent_step(
            messages=[HumanMessage(content=synthesis_prompt)],
            system_persona="You are Jarvis. Present execution results in a clear, natural way. Be concise and user-friendly.",
            tools=None,
            mode="speed"
        )
        
        synthesized_text = engine.llm.sanitize_thought_process(str(synthesis_response.content))
        
        # Combine synthesized text with plot blocks (plots come after) - now just synthesized text
        updated_response = synthesized_text
        
        logger.info("✓ Response synthesized with SPEED LLM")
        
    except Exception as e:
        logger.error(f"Failed to synthesize response: {e}")
        # Fallback to raw output
        updated_response = state.get("final_response", "") + f"\n\n**Execution Result:**\n\n{result}\n"
    
    # Memory saving will be handled async in API layer
    
    # Note: Skill naming and saving will be handled asynchronously in admin_approval node
    # Don't pre-generate skill name here to avoid blocking execution
    
    elapsed = (time.time() - start_time) * 1000
    engine._timing['execute_code'] = elapsed
    logger.info(f"⏱️  execute_code: {elapsed:.1f}ms")
    
    return {
        "execution_result": result_for_llm,  # Pruned for memory (no base64)
        "execution_error": None,  # Clear error flag on success
        "retry_count": retry_count,  # Maintain count but don't increment
        "final_response": updated_response,  # Full with plots for UI
        "generated_code": code,  # Pass code for skill saving
        "existing_skill_code": state.get("existing_skill_code"),
        "used_skill_names": state.get("used_skill_names", []),
        "skill_approved": False  # Will be evaluated in admin_approval
    }


async def admin_approval(engine, state) -> dict:
    """
    Node 5: Admin checkpoint for saving skills using LLM-generated names.
    Handles skill deduplication and async saving.
    """
    import asyncio
    from app.prompts.skill_naming import get_skill_naming_prompt
    
    # Check if skill already exists (from used skills)
    existing_skill = state.get("existing_skill_code")
    used_skills = state.get("used_skill_names", [])
    code = state.get("generated_code", "")
    
    if not code:
        logger.info("No code to save as skill")
        return {"skill_approved": False}
    
    # Check code similarity with existing skills
    if existing_skill:
        code_identical = existing_skill.strip() == code.strip()
        if code_identical:
            logger.info("✓ Skill has identical code to existing, skipping save")
            return {"skill_approved": False}
    
    # Generate skill name using LLM for better naming
    async def generate_and_save_skill():
        try:
            naming_prompt = get_skill_naming_prompt(state["user_input"], code)
            
            naming_response = await engine.llm.run_agent_step(
                messages=[HumanMessage(content=naming_prompt)],
                system_persona="You are a skill naming expert. Generate concise kebab-case names.",
                tools=None,
                mode="speed"
            )
            
            skill_name = engine.llm.sanitize_thought_process(str(naming_response.content)).strip()
            # Clean up any quotes or extra characters
            skill_name = skill_name.replace('"', '').replace("'", '').strip()
            
            # Check if this skill name was already used in this request
            if skill_name in used_skills:
                logger.info(f"✓ Skill '{skill_name}' found in used_skill_names, skipping save")
                return
            
            logger.info(f"Saving skill with LLM-generated name: '{skill_name}'")
            
            engine.skills.save_skill(
                name=skill_name,
                code=code,
                description=state["user_input"]
            )
            
            logger.info(f"✓ Skill '{skill_name}' saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save skill: {e}")
    
    # Run skill saving asynchronously (non-blocking)
    # TODO: Undo this comment
    # asyncio.create_task(generate_and_save_skill())
    
    return {"skill_approved": False}
