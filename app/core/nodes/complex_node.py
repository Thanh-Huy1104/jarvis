"""Complex reasoning and code execution nodes"""

import logging
import time
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.utils.code_extraction import extract_code, generate_skill_name
from app.core.utils.code_transform import ensure_print_output

logger = logging.getLogger(__name__)


async def reason_and_code(engine, state) -> dict:
    """
    Node 3: Thinking mode - LLM plans and generates Python code.
    Checks skill library for relevant snippets first (supports multi-skill combination).
    """
    start_time = time.time()
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

MATPlOTLIB PLOTS:
- DO NOT use plt.show() - the sandbox is headless and cannot display plots
- Instead, SAVE plots to /workspace/plot.png using plt.savefig('/workspace/plot.png')
- The system will automatically detect and display the saved plot.
- Example:
  plt.figure()
  plt.plot(data)
  plt.savefig('/workspace/plot.png')

IMPORTANT: Only write Python code for sandbox execution. If the task requires host system access 
(reading/writing host files, git operations, docker management), explicitly state that MCP tools 
are needed and DO NOT generate Python code. Instead, describe what MCP tools should be used.

Keep your response concise and user-friendly. Do NOT output your internal reasoning process.
"""
    
    system_msg = SystemMessage(content="You are Jarvis, an expert AI assistant with a Python sandbox and MCP tools for host access. Prefer Python sandbox for most tasks. Use MCP tools only when you need to access the host filesystem, run shell commands, or manage Docker containers.")
    user_msg = HumanMessage(content=prompt)
    
    response = await engine.llm.run_agent_step(
        messages=[user_msg],
        system_persona=str(system_msg.content),
        tools=None,
        mode="think"  # Use deep reasoning mode
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
    """
    start_time = time.time()
    code = state.get("generated_code", "")
    
    if not code:
        logger.info("No code to execute")
        return {"execution_result": "No code was generated."}
    
    # # Auto-inject prints if code doesn't have them
    # code = ensure_print_output(code)
    
    logger.info(f"Executing code in sandbox ({len(code)} chars)")
    
    result = engine.sandbox.execute_with_packages(code)
    
    logger.info(f"Execution result: {result[:100]}...")
    
    # Check if plots were generated (base64 encoded in result)
    plot_detected = "[PLOT:" in result and "data:image/png;base64," in result
    
    if plot_detected:
        logger.info("📊 Plot(s) detected and base64 encoded in output")
    
    # Extract plot blocks for final response (keep full base64 for UI)
    import re
    plot_blocks = re.findall(r'\[PLOT:.*?\].*?\[/PLOT:.*?\]', result, re.DOTALL)
    
    # Strip base64 data from result for LLM synthesis (too large for context)
    result_for_llm = re.sub(
        r'data:image/png;base64,[A-Za-z0-9+/=]+',
        'data:image/png;base64,[BASE64_DATA_REMOVED]',
        result
    )
    
    # Clean up "Plot saved to..." messages from output to prevent LLM hallucinations
    result_for_llm = re.sub(r'Plot saved to /workspace/.*?\n?', '', result_for_llm)
    
    # Use SPEED LLM to synthesize a natural response from raw execution output
    synthesis_prompt = f"""The user asked: {state['user_input']}

Code was executed and produced this output:
{result_for_llm}

Create a clear, natural response that:
1. Answers the user's question directly
2. Presents the data in an easy-to-read format
3. Highlights key findings or important information
4. If there are plots, mention: "I've generated a visualization for you."
5. Keep it concise but informative

DO NOT include the raw code or technical details unless relevant.
"""
    
    try:
        synthesis_response = await engine.llm.run_agent_step(
            messages=[HumanMessage(content=synthesis_prompt)],
            system_persona="You are Jarvis. Present execution results in a clear, natural way. Be concise and user-friendly.",
            tools=None,
            mode="speed"
        )
        
        synthesized_text = engine.llm.sanitize_thought_process(str(synthesis_response.content))
        
        # Combine synthesized text with plot blocks (plots come after)
        updated_response = synthesized_text
        if plot_detected and plot_blocks:
            updated_response += "\n\n" + "\n\n".join(plot_blocks)
        
        logger.info("✓ Response synthesized with SPEED LLM")
        
    except Exception as e:
        logger.error(f"Failed to synthesize response: {e}")
        # Fallback to raw output
        updated_response = state.get("final_response", "") + f"\n\n**Execution Result:**\n\n{result}\n"
    
    # Memory saving will be handled async in API layer
    
    # Check if this skill already exists by name AND code
    skill_name = generate_skill_name(state["user_input"])
    existing_skill = state.get("existing_skill_code")
    
    # Skip save if:
    # 1. Skill name matches any of the skills used in this request
    # 2. Exact same code already exists
    skip_approval = False
    
    # Check if skill name exists in used_skill_names
    used_skills = state.get("used_skill_names", [])
    if skill_name in used_skills:
        logger.info(f"✓ Skill '{skill_name}' found in used_skill_names, skipping save")
        skip_approval = True
    elif existing_skill:
        # Check code similarity
        code_identical = existing_skill.strip() == code.strip()
        if code_identical:
            logger.info(f"✓ Skill '{skill_name}' has identical code, skipping save")
            skip_approval = True
        else:
            logger.info(f"Skill '{skill_name}' exists but code differs, will save new version")
    else:
        logger.info(f"No existing skill found, will save as new\n")
    
    elapsed = (time.time() - start_time) * 1000
    engine._timing['execute_code'] = elapsed
    logger.info(f"⏱️  execute_code: {elapsed:.1f}ms")
    
    return {
        "execution_result": result_for_llm,  # Pruned for memory (no base64)
        "final_response": updated_response,  # Full with plots for UI
        "pending_skill_name": skill_name,
        "skill_approved": skip_approval
    }


def admin_approval(engine, state) -> dict:
    """
    Node 5: Admin checkpoint for saving skills.
    Skips if skill already exists or was auto-approved.
    """
    # Check if already approved (from executor)
    if state.get("skill_approved", False):
        logger.info("Skill already approved/exists, skipping save")
        return {"skill_approved": True}
    
    logger.info("Saving new skill to library")
    
    skill_name = state.get("pending_skill_name") or generate_skill_name(state["user_input"])
    
    engine.skills.save_skill(
        name=skill_name,
        code=state["generated_code"],
        description=state["user_input"]
    )
    
    logger.info(f"Skill '{skill_name}' saved successfully")
    
    return {
        "pending_skill_name": skill_name,
        "skill_approved": True
    }
