"""Parallel execution nodes for breaking tasks into concurrent subtasks"""

import json
import re
import logging
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
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
    Executes a single subtask in parallel with skill awareness and self-correction.
    """
    logger.info("="*60)
    logger.info(f"WORKER STARTED: [{task['id']}]")
    logger.info(f"Description: {task['description']}")
    logger.info("="*60)
    
    if status_callback:
        await status_callback(task['id'], 'running')

    # 1. Find relevant skills for this specific subtask
    relevant_skills = engine.skills.find_top_skills(task['description'], n=2, threshold=1.5)
    skills_section = ""
    if relevant_skills:
        logger.info(f"[{task['id']}] Found {len(relevant_skills)} relevant skills")
        for i, skill in enumerate(relevant_skills, 1):
            skills_section += f"\n--- Skill {i}: {skill['name']} ---\n"
            skills_section += f"```python\n{skill['code']}\n```\n"

    retry_count = 0
    max_retries = 1
    current_error = None
    messages = []

    while retry_count <= max_retries:
        if retry_count > 0:
            logger.info(f"[{task['id']}] 🔄 RETRYING worker task (attempt {retry_count}/{max_retries})")
            # Add error feedback to messages
            messages.append(AIMessage(content=f"Previous code execution failed with error:\n\n```\n{current_error}\n```\n\nPlease fix the issue."))
        
        # 2. Generate Prompt
        prompt = get_parallel_worker_prompt(
            task_description=task['description'],
            code_hint=task.get('code_hint', 'Write clean Python code'),
            task_id=task['id'],
            skills_section=skills_section
        )
        
        # 3. Generate Code
        messages.append(HumanMessage(content=prompt))
        
        response = await engine.llm.run_agent_step(
            messages=messages,
            system_persona="You are a code generator. Output ONLY Python code in markdown blocks. No explanations. Use print() to display results.",
            tools=None,
            mode="think"
        )
        
        clean_content = engine.llm.sanitize_thought_process(str(response.content))
        code = extract_code(clean_content, engine.llm)
        
        if not code:
            error_msg = f"Failed to extract code from: {clean_content[:100]}..."
            if retry_count < max_retries:
                current_error = error_msg
                retry_count += 1
                continue
            return {"id": task["id"], "status": "failed", "result": error_msg, "code": ""}

        # 4. Execute Code
        try:
            logger.info(f"[{task['id']}] Executing code (attempt {retry_count + 1})")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, engine.sandbox.execute_with_packages, code)
            
            # 5. Detect Errors in Result (even if exit code was 0)
            error_indicators = ["Error:", "Traceback", "Exception:", "SyntaxError", "ImportError"]
            has_error = any(indicator in result for indicator in error_indicators)
            
            if has_error:
                logger.warning(f"[{task['id']}] ⚠️ Execution error detected in output")
                if retry_count < max_retries:
                    current_error = result
                    retry_count += 1
                    continue
                # If we've exhausted retries, return as failed
                if status_callback:
                    await status_callback(task['id'], 'failed')
                return {"id": task["id"], "status": "failed", "result": result, "code": code}

            # Success!
            logger.info(f"[{task['id']}] ✓ Worker task complete")
            if status_callback:
                await status_callback(task['id'], 'complete')
            return {"id": task["id"], "status": "complete", "result": result, "code": code}

        except Exception as e:
            logger.error(f"[{task['id']}] ❌ Critical execution error: {e}")
            if retry_count < max_retries:
                current_error = str(e)
                retry_count += 1
                continue
            if status_callback:
                await status_callback(task['id'], 'failed')
            return {"id": task["id"], "status": "failed", "result": str(e), "code": code}

    return {"id": task["id"], "status": "failed", "result": "Max retries exceeded", "code": ""}


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
    
    # Check if user explicitly asked for code
    include_code = any(kw in state['user_input'].lower() for kw in ["code", "show code", "how you did it", "debug", "python"])
    
    for i, result in enumerate(successful_tasks, 1):
        task_desc = next((t['description'] for t in plan if t['id'] == result['id']), result['id'])
        results_context += f"Task {i}: {task_desc}\n"
        if include_code:
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
