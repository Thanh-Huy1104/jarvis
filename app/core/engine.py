"""
Jarvis Engine
-------------
Main orchestration engine using LangGraph with code-first approach.

SKILLS vs MCP PHILOSOPHY:
- Skills (.jarvis/skills/*.md): Python code snippets for common tasks
  - Web search, news search, data analysis, web scraping, system monitoring
  - Loaded into ChromaDB on startup, retrieved via semantic search
  - Preferred approach: most tasks should be done via Python skills
  
- MCP Tools: Only for system-level operations that require host access
  - File system operations (read/write files on host)
  - Shell commands (git, apt, system config)
  - Docker container management
  - Used sparingly when skills can't accomplish the task
"""

import json
import re
import logging
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from app.core.state import AgentState, SubTask
from app.core.router import JarvisRouter
from app.core.skills import SkillLibrary
from app.adapters.llm_vllm import VllmAdapter
from app.adapters.memory_mem0 import Mem0Adapter
from app.adapters.mcp_client import JarvisMCPClient
from app.execution.sandbox import DockerSandbox

logger = logging.getLogger(__name__)


class JarvisEngine:
    """
    The main Jarvis orchestration engine.
    Uses LangGraph for workflow, semantic routing for optimization,
    and Docker sandbox for safe code execution.
    """
    
    def __init__(self):
        self.router = JarvisRouter()
        self.llm = VllmAdapter()
        self.memory = Mem0Adapter()
        self.skills = SkillLibrary()
        self.sandbox = DockerSandbox()
        self.mcp = JarvisMCPClient()
        self._task_callback = None  # Store callback here instead of state
        
        logger.info("JarvisEngine initialized")

    # =========================================================================
    # NODES
    # =========================================================================

    def route_query(self, state: AgentState) -> dict:
        """
        Node 1: Classifies user intent as 'speed' or 'complex'.
        Uses 7B LLM with conversation context for accurate routing.
        """
        # Build conversation context from existing messages in state
        # The checkpointer should restore previous messages
        messages = state.get("messages", [])
        context = ""
        
        if messages:
            # Get the last few messages for context (up to 4 messages = 2 exchanges)
            recent = messages[-4:] if len(messages) > 4 else messages
            context_lines = []
            for msg in recent:
                role = "User" if msg.type == "human" else "Assistant"
                content = msg.content[:150] if hasattr(msg, 'content') else str(msg)[:150]
                context_lines.append(f"{role}: {content}")
            context = "\n".join(context_lines)
            logger.debug(f"Router context: {context[:200]}")
        
        intent = self.router.classify(state["user_input"], conversation_context=context)
        logger.info(f"Router classified as: {intent}")
        return {"intent_mode": intent}

    async def speed_response(self, state: AgentState) -> dict:
        """
        Node 2a: Fast path for simple queries (greetings, commands).
        Uses speed mode with low token limit.
        """
        logger.info("Taking SPEED path")
        
        # Simple system prompt
        system_msg = SystemMessage(content="You are Jarvis, a helpful AI assistant. Be concise and friendly.")
        user_msg = HumanMessage(content=state["user_input"])
        
        response = await self.llm.run_agent_step(
            messages=[user_msg],
            system_persona=str(system_msg.content),
            tools=None,
            mode="speed"
        )
        
        # Save to memory
        self.memory.add(
            text=f"User: {state['user_input']}\nAssistant: {response.content}",
            user_id=state["user_id"]
        )
        
        return {
            "final_response": response.content,
            "messages": [user_msg, response]
        }

    async def build_context(self, state: AgentState) -> dict:
        """
        Node 2b: Builds the Context Sandwich for complex queries.
        Retrieves from memory (vector + graph) and adds directives.
        """
        logger.info("Building context sandwich")
        
        ctx_data = self.memory.get_context(
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

    async def reason_and_code(self, state: AgentState) -> dict:
        """
        Node 3: Thinking mode - LLM plans and generates Python code.
        Checks skill library for relevant snippets first (supports multi-skill combination).
        """
        logger.info("Entering THINK mode - generating code")
        
        # Search for multiple relevant skills (top 3)
        relevant_skills = self.skills.find_top_skills(state["user_input"], n=3, threshold=1.2)
        
        # Build skills section for prompt
        if relevant_skills:
            logger.info(f"Found {len(relevant_skills)} relevant skills: ")
            for skill in relevant_skills:
                logger.info(f"- {skill['name']}")
            skills_section = "\n\nRELEVANT SKILLS FROM LIBRARY (combine/modify as needed):\n"
            for i, skill in enumerate(relevant_skills, 1):
                skills_section += f"\n--- Skill {i}: {skill['name']} (similarity: {1 - float(skill['distance']):.2f}) ---\n"
                skills_section += f"```python\n{skill['code']}\n```\n"
            # Store first skill code for deduplication check
            existing_skill_code = relevant_skills[0]['code']
        else:
            skills_section = ""
            existing_skill_code = None
            logger.info("No relevant skills found in library")
        
        # Build enhanced prompt
        directives_str = "\n".join(f"- {d}" for d in state.get("global_directives", []))
        
        prompt = f"""
TASK: {state['user_input']}

{state.get('memory_context', '')}

CORE DIRECTIVES:
{directives_str}

AVAILABLE CAPABILITIES:

1. Python Sandbox (PREFERRED for most tasks):
   Pre-installed packages: psutil, numpy, pandas, matplotlib, scipy, scikit-learn,
   requests, httpx, beautifulsoup4, ddgs, wikipedia, boto3, google-api-python-client,
   psycopg2, pymongo, redis, sqlalchemy, openpyxl, pillow, pyyaml
   
   Use for:
   - Web search (DDGS().text() or DDGS().news())
   - Web scraping (BeautifulSoup)
   - Data analysis (pandas, numpy)
   - API calls (requests, httpx)
   - System monitoring inside sandbox (psutil)

2. MCP Tools (ONLY for host system operations):
   Available when Python sandbox cannot access host system:
   - list_directory(path) - List files on HOST filesystem
   - read_file(filepath) - Read files from HOST
   - write_file(filepath, content) - Write files to HOST
   - run_shell_command(command) - Execute shell on HOST (git, apt, etc.)
   - manage_docker(action, container_name) - Control Docker containers
   
   Use ONLY when you need to:
   - Access files outside the sandbox (host filesystem)
   - Run git commands or system package managers
   - Manage Docker containers
   - Execute system-level operations

DECISION GUIDE:
- Default to Python sandbox code for 90% of tasks
- Use MCP tools ONLY when you need host system access

{skills_section}

Provide a clear, well-formatted response. If you need to write code:
1. Briefly explain what you'll do (1-2 sentences)
2. Write the Python code in a ```python``` code block
3. You can combine/modify the reference skills above if they're helpful
4. Import any packages you need - they're pre-installed or will auto-install

CRITICAL CODE REQUIREMENTS:
- ALWAYS use print() to display results - without print(), the user sees no output!
- Store results in variables AND print them
- Example: result = function(); print(result)
- For functions that return data, call them and print the result

IMPORTANT: Only write Python code for sandbox execution. If the task requires host system access 
(reading/writing host files, git operations, docker management), explicitly state that MCP tools 
are needed and DO NOT generate Python code. Instead, describe what MCP tools should be used.

Keep your response concise and user-friendly. Do NOT output your internal reasoning process.
"""
        
        system_msg = SystemMessage(content="You are Jarvis, an expert AI assistant with a Python sandbox and MCP tools for host access. Prefer Python sandbox for most tasks. Use MCP tools only when you need to access the host filesystem, run shell commands, or manage Docker containers.")
        user_msg = HumanMessage(content=prompt)
        
        response = await self.llm.run_agent_step(
            messages=[user_msg],
            system_persona=str(system_msg.content),
            tools=None,
            mode="think"  # Use deep reasoning mode
        )
        
        # Sanitize thinking process (remove <think> tags if present)
        clean_content = self.llm.sanitize_thought_process(str(response.content))
        
        # Extract Python code block
        code = self._extract_code(clean_content)
        
        logger.info(f"Generated code: {len(code)} characters")
        
        return {
            "generated_code": code,
            "final_response": clean_content,
            "messages": [user_msg, AIMessage(content=clean_content)],
            "existing_skill_code": existing_skill_code
        }

    def execute_code(self, state: AgentState) -> dict:
        """
        Node 4: Executes generated Python code in Docker sandbox.
        """
        code = state.get("generated_code", "")
        
        if not code:
            logger.info("No code to execute")
            return {"execution_result": "No code was generated."}
        
        logger.info(f"Executing code in sandbox ({len(code)} chars)")
        
        result = self.sandbox.execute_with_packages(code)
        
        logger.info(f"Execution result: {result[:100]}...")
        
        # Append execution result to response
        updated_response = state.get("final_response", "") + f"\n\n**Execution Result:**\n```\n{result}\n```"
        
        # Memory saving will be handled async in API layer
        
        # Check if this skill already exists (use cached result from state)
        skill_name = self._generate_skill_name(state["user_input"])
        existing_skill = state.get("existing_skill_code")
        
        # If skill exists and code is similar, skip approval
        if existing_skill:
            logger.info(f"Comparing codes - existing length: {len(existing_skill)}, new length: {len(code)}")
            skip_approval = existing_skill.strip() == code.strip()
            if skip_approval:
                logger.info(f"Skill '{skill_name}' already exists with identical code, skipping save")
            else:
                logger.info(f"Skill '{skill_name}' exists but code differs, will save new version")
        else:
            skip_approval = False
            logger.info(f"No existing skill found, will save as new")
        
        return {
            "execution_result": result,
            "final_response": updated_response,
            "pending_skill_name": skill_name,
            "skill_approved": skip_approval
        }

    def admin_approval(self, state: AgentState) -> dict:
        """
        Node 5: Admin checkpoint for saving skills.
        Skips if skill already exists or was auto-approved.
        """
        # Check if already approved (from executor)
        if state.get("skill_approved", False):
            logger.info("Skill already approved/exists, skipping save")
            return {"skill_approved": True}
        
        logger.info("Saving new skill to library")
        
        skill_name = state.get("pending_skill_name") or self._generate_skill_name(state["user_input"])
        
        self.skills.save_skill(
            name=skill_name,
            code=state["generated_code"],
            description=state["user_input"]
        )
        
        logger.info(f"Skill '{skill_name}' saved successfully")
        
        return {
            "pending_skill_name": skill_name,
            "skill_approved": True
        }

    async def call_mcp_tools(self, state: AgentState) -> dict:
        """
        Node: Execute MCP tools for host system operations.
        Only used when tasks require host filesystem, shell, or docker access.
        """
        logger.info("="*60)
        logger.info("MCP TOOL EXECUTION")
        logger.info("="*60)
        
        try:
            # Connect to MCP servers if not already connected
            if not self.mcp.sessions:
                logger.info("Connecting to MCP servers...")
                await self.mcp.connect()
            
            # Get available tools
            tools = await self.mcp.list_tools()
            logger.info(f"Available MCP tools: {[t['name'] for t in tools]}")
            
            # Build prompt with available tools
            tools_desc = "\n".join([
                f"- {t['name']}: {t['description']}"
                for t in tools
            ])
            
            prompt = f"""
TASK: {state['user_input']}

AVAILABLE MCP TOOLS:
{tools_desc}

Analyze the task and determine which MCP tool(s) to call.
Respond with a JSON object containing the tool calls:

{{
    "tool_calls": [
        {{"name": "tool_name", "args": {{"arg1": "value1"}}}}
    ]
}}

If the task doesn't require MCP tools, respond with {{"tool_calls": []}}.
"""
            
            # Ask LLM to decide which tools to call
            system_msg = SystemMessage(content="You are a tool execution planner. Analyze tasks and determine which MCP tools to call. Respond ONLY with valid JSON.")
            user_msg = HumanMessage(content=prompt)
            
            response = await self.llm.run_agent_step(
                messages=[user_msg],
                system_persona=str(system_msg.content),
                tools=None,
                mode="speed"
            )
            
            # Parse tool calls from response
            clean_response = self.llm.sanitize_thought_process(str(response.content))
            tool_plan = self._extract_json(clean_response)
            
            if not tool_plan or not tool_plan.get("tool_calls"):
                return {
                    "final_response": "No MCP tools needed for this task.",
                    "execution_result": ""
                }
            
            # Execute each tool call
            results = []
            for tool_call in tool_plan["tool_calls"]:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                
                logger.info(f"Calling MCP tool: {tool_name}({tool_args})")
                result = await self.mcp.call_tool(tool_name, tool_args)
                results.append(f"**{tool_name}:**\n{result}")
            
            combined_result = "\n\n".join(results)
            
            return {
                "execution_result": combined_result,
                "final_response": f"MCP Tool Results:\n\n{combined_result}"
            }
            
        except Exception as e:
            logger.error(f"MCP tool execution error: {e}")
            return {
                "execution_result": f"Error: {str(e)}",
                "final_response": f"Failed to execute MCP tools: {str(e)}"
            }

    # =========================================================================
    # PARALLEL EXECUTION NODES
    # =========================================================================

    async def plan_parallel_tasks(self, state: AgentState) -> dict:
        """
        Analyzes if task can be broken into parallel subtasks.
        Returns a plan with multiple independent tasks or single task.
        """
        logger.info("="*60)
        logger.info("PARALLEL PLANNING STARTED")
        logger.info(f"User input: {state['user_input']}")
        logger.info("="*60)
        
        planning_prompt = f"""Analyze this task and determine if it can be broken into independent parallel subtasks:

Task: {state['user_input']}

If the task involves multiple INDEPENDENT operations that can run simultaneously (e.g., "fetch Bitcoin AND Ethereum prices", "generate 3 different charts"), break it into subtasks.

If the task is sequential or single-operation, return a single task.

Respond ONLY with valid JSON, no explanations:
{{
  "parallel": true/false,
  "subtasks": [
    {{"id": "task_1", "description": "...", "code_hint": "..."}},
    {{"id": "task_2", "description": "...", "code_hint": "..."}}
  ]
}}"""
        
        response = await self.llm.run_agent_step(
            messages=[HumanMessage(content=planning_prompt)],
            system_persona="You are a task planning expert. Output ONLY valid JSON, no thinking process, no explanations.",
            tools=None,
            mode="speed"  # Use speed model for quick JSON parsing
        )
        
        try:
            # Sanitize thinking tags first
            content = self.llm.sanitize_thought_process(str(response.content))
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

    async def execute_parallel_worker(self, state: AgentState, task: SubTask, status_callback=None) -> dict:
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
        prompt = f"""Write ONLY the Python code for this task:

Task: {task['description']}
Hint: {task.get('code_hint', 'Write clean Python code')}

Available packages (pre-installed):
- psutil, numpy, pandas, matplotlib, requests, httpx
- ddgs (use: from ddgs import DDGS), wikipedia, beautifulsoup4
- boto3, google-api-python-client, psycopg2, pymongo

CRITICAL: Use print() to display results - without print(), output is invisible!
Example: result = function(); print(result)

Import what you need and write the code. Respond with ONLY a Python code block, nothing else. No explanations."""
        
        response = await self.llm.run_agent_step(
            messages=[HumanMessage(content=prompt)],
            system_persona="You are a code generator with access to a Python sandbox. Output ONLY Python code in markdown blocks. No explanations, no thinking process. All common packages are pre-installed. ALWAYS use print() to display results.",
            tools=None,
            mode="think"
        )
        
        # Sanitize thinking tags first, then extract code
        clean_content = self.llm.sanitize_thought_process(str(response.content))
        logger.info(f"[{task['id']}] LLM response length: {len(str(response.content))} chars")
        logger.info(f"[{task['id']}] Clean content preview: {clean_content[:200]}...")
        
        code = self._extract_code(clean_content)
        
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
            import asyncio
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(None, self.sandbox.execute_with_packages, code)
            
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

    async def aggregate_parallel_results(self, state: AgentState) -> dict:
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
        status_callback = self._task_callback
        logger.info(f"Task callback available: {status_callback is not None}")
        
        # Execute all subtasks concurrently
        import asyncio
        logger.info(f"Creating {len(plan)} worker tasks...")
        for i, task in enumerate(plan, 1):
            logger.info(f"  Worker {i}: [{task['id']}] {task['description']}")
        
        tasks = [self.execute_parallel_worker(state, task, status_callback) for task in plan]
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
        synthesis_prompt = f"""You executed multiple tasks in parallel. Analyze the results and provide a clear, insightful summary.

{results_context}

Provide a natural response that:
1. Acknowledges what was done in parallel
2. For EACH task, show the code that was generated and its output
3. Highlight interesting findings or patterns in the results
4. Answer the user's original question directly

Format each task's output like this:
**Task: [description]**
```python
[the actual code]
```
**Output:**
```
[the result]
```

Be concise but informative. Show all code blocks and results."""
        
        logger.info("Synthesizing results with AI")
        response = await self.llm.run_agent_step(
            messages=[HumanMessage(content=synthesis_prompt)],
            system_persona="You are Jarvis, an AI assistant. Analyze parallel task results and provide clear, insightful summaries.",
            tools=None,
            mode="speed"  # Use fast model for synthesis
        )
        
        synthesized_response = self.llm.sanitize_thought_process(str(response.content))
        
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
        
        return {
            "execution_result": all_results,
            "final_response": combined_response
        }

    # =========================================================================
    # EDGE LOGIC
    # =========================================================================

    def route_by_intent(self, state: AgentState) -> Literal["speed_agent", "context_builder"]:
        """Conditional edge: Route based on intent classification"""
        return "speed_agent" if state["intent_mode"] == "speed" else "context_builder"

    def should_parallelize(self, state: AgentState) -> Literal["parallel_planner", "think_agent"]:
        """Conditional edge: Check if task should be parallelized"""
        logger.info("="*60)
        logger.info("ROUTING: should_parallelize")
        logger.info(f"User input: {state['user_input']}")
        
        # Check for keywords suggesting parallel tasks
        user_input = state["user_input"].lower()
        parallel_keywords = ["and", "multiple", "both", "all", "simultaneously", "parallel"]
        
        keywords_found = [kw for kw in parallel_keywords if kw in user_input]
        logger.info(f"Keywords found: {keywords_found}")
        
        # Only parallelize if explicitly requested or multiple independent tasks detected
        if any(keyword in user_input for keyword in parallel_keywords):
            # Further check: count "and" or commas suggesting multiple items
            and_count = user_input.count(" and ")
            comma_count = user_input.count(",")
            logger.info(f"AND count: {and_count}, Comma count: {comma_count}")
            
            if and_count > 0 or comma_count > 1:
                logger.info("→ DECISION: parallel_planner")
                logger.info("="*60)
                return "parallel_planner"
        
        # Default: sequential execution
        logger.info("→ DECISION: think_agent (sequential)")
        logger.info("="*60)
        return "think_agent"

    def route_after_planning(self, state: AgentState) -> Literal["parallel_executor", "think_agent"]:
        """Conditional edge: Execute in parallel or sequential"""
        logger.info("="*60)
        logger.info("ROUTING: route_after_planning")
        
        plan = state.get("plan", [])
        logger.info(f"Plan in state: {plan}")
        logger.info(f"Plan length: {len(plan)}")
        logger.info(f"Plan type: {type(plan)}")
        
        if plan:
            for i, task in enumerate(plan, 1):
                logger.info(f"  Task {i}: {task}")
        
        if plan and len(plan) > 1:
            logger.info(f"→ DECISION: parallel_executor ({len(plan)} tasks)")
            logger.info("="*60)
            return "parallel_executor"
        else:
            logger.info("→ DECISION: think_agent (sequential)")
            logger.info("="*60)
            return "think_agent"

    def should_save_skill(self, state: AgentState) -> Literal["admin_save", "end"]:
        """Conditional edge: Save skill if code was generated and is novel"""
        if state.get("generated_code") and len(state["generated_code"]) > 50:
            # In production, check if skill already exists or is trivial
            return "admin_save"
        return "end"

    # =========================================================================
    # BUILD GRAPH
    # =========================================================================

    def build(self):
        """
        Constructs the LangGraph workflow.
        
        Returns:
            Compiled graph with checkpointer and interrupt
        """
        workflow = StateGraph(AgentState)
        
        # Add all nodes
        workflow.add_node("router", self.route_query)
        workflow.add_node("speed_agent", self.speed_response)
        workflow.add_node("context_builder", self.build_context)
        workflow.add_node("parallel_planner", self.plan_parallel_tasks)
        workflow.add_node("think_agent", self.reason_and_code)
        workflow.add_node("executor", self.execute_code)
        workflow.add_node("parallel_executor", self.aggregate_parallel_results)  # Placeholder for now
        
        # Entry point
        workflow.add_edge(START, "router")
        
        # Conditional routing by intent
        workflow.add_conditional_edges(
            "router",
            self.route_by_intent,
            {
                "speed_agent": "speed_agent",
                "context_builder": "context_builder"
            }
        )
        
        # Complex path: context → parallel planning → route based on plan
        workflow.add_conditional_edges(
            "context_builder",
            self.should_parallelize,
            {
                "parallel_planner": "parallel_planner",
                "think_agent": "think_agent"
            }
        )
        
        # After planning: execute in parallel or sequential
        workflow.add_conditional_edges(
            "parallel_planner",
            self.route_after_planning,
            {
                "parallel_executor": "parallel_executor",
                "think_agent": "think_agent"
            }
        )
        
        # Sequential path
        workflow.add_edge("think_agent", "executor")
        workflow.add_edge("executor", END)
        
        # Parallel path
        workflow.add_edge("parallel_executor", END)
        workflow.add_edge("think_agent", "executor")
        workflow.add_edge("executor", END)
        
        # Terminal edges
        workflow.add_edge("speed_agent", END)

        # Enable persistence with checkpointer
        memory = MemorySaver()
        
        # Compile without interrupts for UI mode (auto-approval in nodes)
        compiled_graph = workflow.compile(
            checkpointer=memory
        )
        
        logger.info("Graph compiled successfully")
        return compiled_graph

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _extract_code(self, text: str) -> str:
        """Extract Python code from markdown code blocks"""
        if not text:
            return ""
        
        # Remove any thinking tags first
        text = self.llm.sanitize_thought_process(text)
        
        # Try standard python code block with newlines
        pattern = r'```python\s*\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return max(matches, key=len).strip()
        
        # Try without language specifier but with newlines
        pattern = r'```\s*\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            # Filter for Python-like code
            for match in sorted(matches, key=len, reverse=True):
                if any(kw in match for kw in ['import', 'def', 'print', 'for', 'if', '=']):
                    return match.strip()
        
        # Try inline code blocks (no newlines)
        pattern = r'```python(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return max(matches, key=len).strip()
        
        # Try generic code block (no language, no newlines)
        pattern = r'```(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            for match in sorted(matches, key=len, reverse=True):
                if any(kw in match for kw in ['import', 'def', 'print', 'for', 'if', '=']):
                    return match.strip()
        
        logger.warning("No code block found in response")
        logger.debug(f"Raw text: {text[:300]}...")
        return ""

    def _generate_skill_name(self, description: str) -> str:
        """Generate a skill name from task description"""
        # Simple slug generation
        slug = re.sub(r'[^a-z0-9]+', '_', description.lower())[:50]
        return slug.strip('_')
    
    def _extract_json(self, text: str) -> dict:
        """Extract JSON object from text (handles markdown code blocks)"""
        if not text:
            return {}
        
        # Remove thinking tags
        text = self.llm.sanitize_thought_process(text)
        
        # Try to find JSON in code blocks first
        json_pattern = r'```(?:json)?\s*\n?(\{.*?\})\s*\n?```'
        matches = re.findall(json_pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass
        
        # Try to find raw JSON object
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        logger.warning("No valid JSON found in text")
        return {}
    
    async def cleanup(self):
        """Cleanup MCP connections and resources"""
        logger.info("Cleaning up JarvisEngine resources")
        try:
            await self.mcp.cleanup()
        except Exception as e:
            logger.error(f"Error during MCP cleanup: {e}")

