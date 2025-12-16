"""Parallel execution nodes for breaking tasks into concurrent subtasks"""

import json
import re
import logging
import asyncio
from langchain_core.messages import HumanMessage
from app.core.state import SubTask
from app.core.utils.code_extraction import extract_code
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
        system_persona="You are a task planning expert. Output ONLY valid JSON, no thinking process, no explanations.",
        tools=None,
        mode="speed"  # Use speed model for quick JSON parsing
    )
    
    try:
        # Sanitize thinking tags first
        content = engine.llm.sanitize_thought_process(str(response.content))
        logger.info(f"LLM response (sanitized): {content[:500]}...")
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            plan_data = json.loads(json_match.group())
            logger.info(f"Parsed plan data: {plan_data}")
            
            if plan_data.get("parallel") and len(plan_data.get("subtasks", [])) > 1:
                logger.info(f"✓ Task can be parallelized into {len(plan_data['subtasks'])} subtasks:")
                for i, task in enumerate(plan_data["subtasks"], 1):
                    logger.info(f"  Task {i}: [{task['id']}] {task['description']}")
                
                subtasks = [
                    SubTask(
                        id=task["id"],
                        description=task["description"],
                        status="pending",
                        result=None
                    ) for task in plan_data["subtasks"]
                ]
                logger.info(f"Created {len(subtasks)} SubTask objects")
                return {"plan": subtasks}
    except Exception as e:
        logger.warning(f"Failed to parse parallel plan: {e}")
        logger.debug(f"Raw response: {str(response.content)[:200]}...")
    
    # Default: Single sequential task
    logger.info("Task will execute sequentially")
    return {"plan": []}


async def execute_parallel_worker(engine, state, task: SubTask, status_callback=None) -> dict:
    """
    Executes a single subtask in parallel.
    This is called multiple times simultaneously.
    Docker exec_run handles concurrent executions safely.
    """
    logger.info("="*60)
    logger.info(f"WORKER STARTED: [{task['id']}]")
    logger.info(f"Description: {task['description']}")
    logger.info(f"Has callback: {status_callback is not None}")
    logger.info("="*60)
    
    # Send task started status update
    if status_callback:
        logger.info(f"Sending 'running' status for [{task['id']}]")
        await status_callback(task['id'], 'running')
    else:
        logger.warning(f"No status callback available for [{task['id']}]")
    
    # Generate code for this specific subtask
    prompt = get_parallel_worker_prompt(
        task_description=task['description'],
        code_hint=task.get('code_hint', 'Write clean Python code'),
        task_id=task['id']
    )
    
    response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=prompt)],
        system_persona="You are a code generator with access to a Python sandbox. Output ONLY Python code in markdown blocks. No explanations, no thinking process. All common packages are pre-installed. ALWAYS use print() to display results.",
        tools=None,
        mode="think"
    )
    
    # Sanitize thinking tags first, then extract code
    clean_content = engine.llm.sanitize_thought_process(str(response.content))
    logger.info(f"[{task['id']}] LLM response length: {len(str(response.content))} chars")
    logger.info(f"[{task['id']}] Clean content preview: {clean_content[:200]}...")
    
    code = extract_code(clean_content, engine.llm)
    
    if not code:
        logger.error(f"[{task['id']}] ❌ FAILED: No code could be extracted")
        logger.error(f"[{task['id']}] Full clean content: {clean_content}")
        if status_callback:
            logger.info(f"Sending 'failed' status for [{task['id']}]")
            await status_callback(task['id'], 'failed')
        return {
            "id": task["id"],
            "status": "failed",
            "result": "Failed to generate code",
            "code": ""
        }
    
    logger.info(f"[{task['id']}] ✓ Code extracted: {len(code)} chars")
    logger.info(f"[{task['id']}] Code preview:\n{code[:300]}...")
    
    try:
        # Execute in sandbox with automatic package installation
        logger.info(f"[{task['id']}] Starting sandbox execution with package detection...")
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(None, engine.sandbox.execute_with_packages, code)
        
        logger.info(f"[{task['id']}] ✓ EXECUTION COMPLETE")
        logger.info(f"[{task['id']}] Result length: {len(result)} chars")
        logger.info(f"[{task['id']}] Result preview:\n{result[:500]}...")
        
        # Send task completed status update
        if status_callback:
            logger.info(f"Sending 'complete' status for [{task['id']}]")
            await status_callback(task['id'], 'complete')
        else:
            logger.warning(f"[{task['id']}] No callback to send 'complete' status")
        
        return {
            "id": task["id"],
            "status": "complete",
            "result": result,
            "code": code
        }
    except Exception as e:
        logger.error(f"[{task['id']}] ❌ EXECUTION ERROR: {type(e).__name__}: {e}")
        logger.error(f"[{task['id']}] Traceback:", exc_info=True)
        if status_callback:
            logger.info(f"Sending 'failed' status for [{task['id']}]")
            await status_callback(task['id'], 'failed')
        return {
            "id": task["id"],
            "status": "failed",
            "result": f"Execution error: {str(e)}",
            "code": code
        }


async def aggregate_parallel_results(engine, state) -> dict:
    """
    Combines results from parallel execution with AI synthesis.
    Executes subtasks in parallel using asyncio, then uses LLM to analyze and present results.
    """
    logger.info("="*60)
    logger.info("PARALLEL EXECUTION STARTED")
    logger.info("="*60)
    
    plan = state.get("plan", [])
    logger.info(f"Plan contains {len(plan)} tasks")
    if not plan:
        logger.warning("No plan found in state, skipping parallel execution")
        return {}
    
    # Use callback stored in engine instance (not from state to avoid serialization issues)
    status_callback = engine._task_callback
    logger.info(f"Task callback available: {status_callback is not None}")
    
    # Execute all subtasks concurrently
    logger.info(f"Creating {len(plan)} worker tasks...")
    for i, task in enumerate(plan, 1):
        logger.info(f"  Worker {i}: [{task['id']}] {task['description']}")
    
    tasks = [execute_parallel_worker(engine, state, task, status_callback) for task in plan]
    logger.info(f"Starting parallel execution of {len(tasks)} workers with asyncio.gather()")
    
    results = await asyncio.gather(*tasks)
    
    logger.info(f"="*60)
    logger.info(f"PARALLEL EXECUTION COMPLETE: {len(results)} results received")
    logger.info(f"="*60)
    
    # Build detailed results for AI analysis
    successful_tasks = [r for r in results if r.get("status") == "complete"]
    failed_tasks = [r for r in results if r.get("status") == "failed"]
    
    logger.info(f"Results breakdown:")
    logger.info(f"  ✓ Successful: {len(successful_tasks)}")
    logger.info(f"  ✗ Failed: {len(failed_tasks)}")
    for i, task_result in enumerate(results, 1):
        logger.info(f"  Result {i}: [{task_result['id']}] status={task_result['status']}")
    
    # Prepare context for AI synthesis
    results_context = f"Original request: {state['user_input']}\n\n"
    results_context += f"Executed {len(successful_tasks)}/{len(plan)} tasks successfully:\n\n"
    
    for i, result in enumerate(successful_tasks, 1):
        task_desc = next((t['description'] for t in plan if t['id'] == result['id']), result['id'])
        results_context += f"Task {i}: {task_desc}\n"
        results_context += f"Code:\n```python\n{result.get('code', '')}\n```\n"
        results_context += f"Result:\n{result.get('result', '')}\n\n"
    
    if failed_tasks:
        results_context += f"\nFailed tasks: {len(failed_tasks)}\n"
        for task in failed_tasks:
            results_context += f"- {task['id']}: {task.get('result', 'Unknown error')}\n"
    
    # Use AI to synthesize and present results intelligently
    synthesis_prompt = get_parallel_synthesis_prompt(state['user_input'], results_context)
    
    logger.info("Synthesizing results with AI")
    response = await engine.llm.run_agent_step(
        messages=[HumanMessage(content=synthesis_prompt)],
        system_persona="You are Jarvis, an AI assistant. Analyze parallel task results and provide clear, insightful summaries.",
        tools=None,
        mode="speed"  # Use fast model for synthesis
    )
    
    synthesized_response = engine.llm.sanitize_thought_process(str(response.content))
    
    # Also keep raw execution_result for compatibility
    execution_result = "\n\n".join([
        f"Task {r['id']}:\n{r.get('result', '')}" 
        for r in successful_tasks
    ])
    
    logger.info(f"AI synthesized {len(successful_tasks)} parallel results")
    
    return {
        "execution_result": execution_result,
        "final_response": synthesized_response
    }
