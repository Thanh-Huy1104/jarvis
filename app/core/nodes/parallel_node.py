"""Parallel execution nodes for breaking tasks into concurrent subtasks"""

import json
import re
import logging
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.core.state import SubTask
from app.core.utils.code_extraction import extract_code
from app.core.utils.executor import execute_with_packages
from app.prompts.parallel import get_parallel_planning_prompt, get_parallel_worker_prompt
from app.prompts.synthesis import get_parallel_synthesis_prompt

logger = logging.getLogger(__name__)


async def plan_parallel_tasks(engine, state) -> dict:
    """
    Analyzes if task can be broken into parallel subtasks.
    Returns a plan with multiple independent tasks or single task.
    """
    logger.info("="*60)
    logger.info("PARALLEL PLANNING STARTED")
    logger.info(f"User input: {state['user_input']}")
    logger.info("="*60)
    
    planning_prompt = get_parallel_planning_prompt(state['user_input'])
    
    response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=planning_prompt)],
        system_persona="You are a task planning expert. Output ONLY valid JSON.",
        tools=None,
        mode="speed"
    )
    
    try:
        content = engine.llm.sanitize_thought_process(str(response.content))
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            plan_data = json.loads(json_match.group())
            
            if plan_data.get("parallel") and len(plan_data.get("subtasks", [])) > 1:
                subtasks = [
                    SubTask(
                        id=task["id"],
                        description=task["description"],
                        code_hint=task.get("code_hint", ""),
                        status="pending",
                        result=None
                    ) for task in plan_data["subtasks"]
                ]
                return {"plan": subtasks}
    except Exception as e:
        logger.warning(f"Failed to parse parallel plan: {e}")
    
    return {"plan": []}


async def execute_parallel_worker(engine, state, task: SubTask, status_callback=None) -> dict:
    """
    Executes a single subtask in parallel with SkillRegistry awareness.
    """
    logger.info(f"WORKER STARTED: [{task['id']}] {task['description']}")
    
    if status_callback:
        await status_callback(task['id'], 'running')

    # 1. Discover tools specific to THIS subtask
    relevant_tools = engine.skills.find_tools(task['description'], n=3)
    tools_section = engine.skills.get_tool_definitions_prompt(relevant_tools)

    retry_count = 0
    max_retries = 1
    current_error = None
    messages = []

    while retry_count <= max_retries:
        if retry_count > 0:
            messages.append(AIMessage(content=f"Previous execution failed: {current_error}. Please fix."))
        
        worker_prompt = (
            f"SUBTASK: {task['description']}\n"
            f"HINT: {task['code_hint']}\n\n"
            f"{tools_section}\n\n"
            "Write Python code for this specific subtask. Call pre-loaded tools directly if needed. "
            "Use print() to output results."
        )
        
        messages.append(HumanMessage(content=worker_prompt))
        
        response = await engine.llm.run_agent_step(
            messages=messages,
            system_persona="You are a Jarvis worker. Output ONLY Python code in markdown blocks. Tools are pre-loaded.",
            mode="think"
        )
        
        clean_content = engine.llm.sanitize_thought_process(str(response.content))
        code = extract_code(clean_content, engine.llm)
        
        if not code:
            if retry_count < max_retries:
                retry_count += 1
                continue
            return {"id": task["id"], "status": "failed", "result": "Code extraction failed"}

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, execute_with_packages, code)
            
            if "Error:" in result or "Traceback" in result:
                if retry_count < max_retries:
                    current_error = result
                    retry_count += 1
                    continue
                if status_callback: await status_callback(task['id'], 'failed')
                return {"id": task["id"], "status": "failed", "result": result, "code": code}

            if status_callback: await status_callback(task['id'], 'complete')
            return {"id": task["id"], "status": "complete", "result": result, "code": code}

        except Exception as e:
            if retry_count < max_retries:
                current_error = str(e)
                retry_count += 1
                continue
            if status_callback: await status_callback(task['id'], 'failed')
            return {"id": task["id"], "status": "failed", "result": str(e), "code": code}

    return {"id": task["id"], "status": "failed", "result": "Max retries exceeded"}


async def aggregate_parallel_results(engine, state) -> dict:
    """
    Combines results from parallel execution with AI synthesis.
    """
    plan = state.get("plan", [])
    if not plan: return {}
    
    status_callback = getattr(engine, '_task_callback', None)
    
    tasks = [execute_parallel_worker(engine, state, task, status_callback) for task in plan]
    results = await asyncio.gather(*tasks)
    
    successful_tasks = [r for r in results if r.get("status") == "complete"]
    failed_tasks = [r for r in results if r.get("status") == "failed"]
    
    results_context = f"Original request: {state['user_input']}\n\n"
    for i, res in enumerate(successful_tasks, 1):
        results_context += f"Task {i}: {res['result']}\n\n"
    
    if failed_tasks:
        results_context += f"\nFailed tasks: {len(failed_tasks)}\n"
    
    synthesis_prompt = get_parallel_synthesis_prompt(state['user_input'], results_context)
    
    response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=synthesis_prompt)],
        system_persona="You are Jarvis. Synthesize subtask results into a final answer.",
        mode="speed"
    )
    
    return {
        "final_response": engine.llm.sanitize_thought_process(str(response.content)),
        "execution_result": results_context
    }
