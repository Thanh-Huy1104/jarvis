"""Complex reasoning and code execution nodes"""

import logging
import time
import datetime
import re
import json
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.utils.code_extraction import extract_code
from app.core.utils.tool_ops import _strip_structural_markers, _execute_tool_calls
from app.core.utils.executor import execute_with_packages
from app.prompts.code_generation import get_code_generation_prompt
from app.prompts.synthesis import get_synthesis_prompt

logger = logging.getLogger(__name__)

async def reason_and_code(engine, state) -> dict:
    """
    Node 3: Thinking mode - LLM plans and generates either:
    1. A JSON list of tool calls (for simple chaining).
    2. Python code (for complex logic).
    """
    start_time = time.time()
    retry_count = state.get("retry_count", 0)
    
    query = state.get("current_task_description", state["user_input"])
    relevant_tools = engine.skills.find_tools(query, n=5)
    tools_section = engine.skills.get_tool_definitions_prompt(relevant_tools)
    
    # Format message history
    messages = state.get("messages", [])
    message_context = ""
    if messages:
        recent_messages = messages[-6:]
        formatted = []
        for msg in recent_messages:
            role = "User" if msg.type == "human" else "Assistant"
            content = str(msg.content)[:500]
            formatted.append(f"{role}: {content}")
        message_context = "\n\nRECENT CONVERSATION:\n" + "\n".join(formatted) + "\n"
        
        if retry_count > 0:
            message_context += "\n⚠️ IMPORTANT: The previous attempt failed. Please fix the issues.\n"
    
    current_date = datetime.date.today().strftime("%B %d, %Y")
    
    system_msg = SystemMessage(content=(
        "You are Jarvis. You can solve tasks in two ways:\n"
        "1. **JSON Tool Chaining (PREFERRED)**: If you just need to call tools sequentially, output a JSON object with a 'tools' key.\n"
        "   Example: {\"tools\": [{\"name\": \"check_stock_price\", \"args\": {\"symbol\": \"AAPL\"}}]}\n"
        "2. **Python Code**: If you need loops, data processing, or complex logic, output Python code in a markdown block.\n\n"
        f"{tools_section}\n"
        "Do NOT import tools in Python code; they are pre-loaded."
    ))
    
    user_prompt = (
        f"Request: {query}\n"
        f"Date: {current_date}\n"
        f"{message_context}\n"
        "Decide: JSON Chaining or Python Code?"
    )
    
    response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=user_prompt)],
        system_persona=str(system_msg.content),
        tools=None,
        mode="think"
    )
    
    clean_content = engine.llm.sanitize_thought_process(str(response.content))
    
    # Check for JSON Tool Chaining
    json_match = re.search(r'\{.*"tools":\s*\[.*\]\s*\}', clean_content, re.DOTALL)
    
    if json_match:
        try:
            data = json.loads(json_match.group())
            tool_calls = data.get("tools", [])
            
            # LOGGING: Print the tool plan
            logger.info("="*50)
            logger.info(f"✓ DETECTED JSON TOOL CHAIN ({len(tool_calls)} steps):")
            for i, call in enumerate(tool_calls, 1):
                logger.info(f"  {i}. {call.get('name')}({call.get('args')})")
            logger.info("="*50)
            
            # Execute Tools Immediately (Bypassing Sandbox for speed)
            execution_result = _execute_tool_calls(tool_calls, engine.skills)
            
            # Synthesize Result
            synthesis_prompt = get_synthesis_prompt(state['user_input'], execution_result)
            synth_response = await engine.llm.run_agent_step(
                messages=[HumanMessage(content=synthesis_prompt)],
                system_persona="Synthesize the tool outputs into a clear answer. DO NOT include technical JSON tool calls in your response.",
                mode="speed"
            )
            raw_text = engine.llm.sanitize_thought_process(str(synth_response.content))
            final_text = _strip_structural_markers(raw_text)
            
            elapsed = (time.time() - start_time) * 1000
            engine._timing['reason_and_code'] = elapsed
            
            return {
                "generated_code": None, 
                "execution_result": execution_result,
                "final_response": final_text,
                "messages": [AIMessage(content=final_text)]
            }
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse detected JSON tool chain, falling back to code extraction")

    # Fallback: Python Code Generation
    code = extract_code(clean_content, engine.llm)
    reasoning_only = _strip_structural_markers(clean_content)
    
    elapsed = (time.time() - start_time) * 1000
    engine._timing['reason_and_code'] = elapsed
    
    return {
        "generated_code": code,
        "final_response": reasoning_only,
        "messages": [AIMessage(content=clean_content)],
        "used_tool_names": [t.name for t in relevant_tools]
    }


async def execute_code(engine, state) -> dict:
    """
    Node 4: Executes generated Python code in Docker sandbox.
    Skipped if JSON chaining was used (generated_code is None).
    """
    code = state.get("generated_code")
    if code is None:
        # JSON Chaining path already handled execution
        return {}
        
    start_time = time.time()
    retry_count = state.get("retry_count", 0)
    
    if not code:
        return {"execution_result": "No code was generated.", "retry_count": retry_count}
    
    logger.info(f"Executing code locally - Attempt {retry_count + 1}")
    result = execute_with_packages(code)
    
    error_indicators = ["Error:", "Traceback", "Exception:", "SyntaxError"]
    has_error = any(indicator in result for indicator in error_indicators)
    
    if has_error:
        error_msg = AIMessage(content=f"Execution failed.\nCODE:\n```python\n{code}\n```\nERROR:\n```\n{result}\n```")
        return {
            "execution_result": result,
            "execution_error": result,
            "retry_count": retry_count + 1,
            "messages": [error_msg]
        }
    
    synthesis_prompt = get_synthesis_prompt(state['user_input'], result)
    synthesis_response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=synthesis_prompt)],
        system_persona="You are Jarvis. Present results clearly and naturally. DO NOT include technical JSON tool calls in your response.",
        mode="speed"
    )
    
    synthesized_text = engine.llm.sanitize_thought_process(str(synthesis_response.content))
    
    elapsed = (time.time() - start_time) * 1000
    engine._timing['execute_code'] = elapsed
    
    return {
        "execution_result": result,
        "execution_error": None,
        "final_response": _strip_structural_markers(synthesized_text), 
        "generated_code": code
    }


async def propose_pending_skill(engine, state):
    """
    Node 5: Proposes new code as a potential skill.
    """
    import asyncio
    from app.prompts.skill_naming import get_skill_naming_prompt
    
    code = state.get("generated_code")
    if not code: return
    
    used_tools = state.get("used_tool_names", [])
    if len(code.split('\n')) < 5: return

    async def generate_and_save():
        try:
            naming_prompt = get_skill_naming_prompt(state["user_input"], code)
            res = await engine.llm.run_agent_step(
                messages=[HumanMessage(content=naming_prompt)],
                system_persona="Generate concise kebab-case names.",
                mode="speed"
            )
            name = engine.llm.sanitize_thought_process(str(res.content)).strip().replace('"', '').replace("'", '')
            
            if name not in used_tools:
                engine.skills.pending.add_pending_skill(code=code, description=state["user_input"], name=name)
        except Exception as e:
            logger.error(f"Failed to propose skill: {e}")
            
    asyncio.create_task(generate_and_save())
