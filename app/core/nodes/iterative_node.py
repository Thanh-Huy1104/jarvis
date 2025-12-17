"""Iterative tool-calling node for deep research and analysis"""

import logging
import time
import datetime
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.utils.code_extraction import extract_code, extract_json
from app.prompts.iterative import get_iterative_prompt, get_continuation_prompt

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5  # Maximum number of tool calls before forcing completion


async def iterative_research(engine, state) -> dict:
    """
    Node: Iterative research and tool calling.
    
    The agent can make multiple sequential tool calls:
    1. Search for information
    2. Scrape specific URLs from results
    3. Analyze data
    4. Continue until satisfied it has fully answered the question
    
    The model decides when it's done by returning final_answer instead of next_action.
    """
    start_time = time.time()
    logger.info("="*60)
    logger.info("ITERATIVE RESEARCH MODE")
    logger.info("="*60)
    
    user_input = state["user_input"]
    context = state.get("memory_context", "")
    
    # Format message history
    messages = state.get("messages", [])
    if messages:
        recent_messages = messages[-4:]  # Last 4 messages
        formatted = []
        for msg in recent_messages:
            role = "User" if msg.type == "human" else "Assistant"
            formatted.append(f"{role}: {str(msg.content)[:150]}")
        context += "\n\nCONVERSATION HISTORY:\n" + "\n".join(formatted) + "\n"
    
    # Get current date
    current_date = datetime.date.today().strftime("%B %d, %Y")
    
    # Search for relevant skills
    relevant_skills = engine.skills.find_top_skills(user_input, n=3, threshold=1.2)
    skills_section = ""
    if relevant_skills:
        logger.info(f"Found {len(relevant_skills)} relevant skills for iterative research")
        skills_section = "\n\nRELEVANT SKILLS (combine/modify as needed):\n"
        for i, skill in enumerate(relevant_skills, 1):
            skills_section += f"\n--- Skill {i}: {skill['name']} ---\n"
            skills_section += f"```python\n{skill['code']}\n```\n"

    # Track the research history
    research_history = []
    iteration = 0
    
    # Initial prompt
    current_prompt = get_iterative_prompt(
        user_input=user_input, 
        memory_context=context,
        current_date=current_date,
        skills_section=skills_section
    )
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"ITERATION {iteration}/{MAX_ITERATIONS}")
        logger.info(f"{'='*60}\n")
        
        # Ask model to decide next action
        system_msg = SystemMessage(content=f"""You are Jarvis, a research assistant with access to Python tools. 
You can make multiple tool calls to thoroughly research and answer questions.

Available capabilities:
- Web search (duckduckgo_search)
- Web scraping (requests + BeautifulSoup)  
- Data analysis (pandas, numpy)

You can iterate:
1. Search for information
2. Scrape specific URLs to get detailed content
3. Analyze and synthesize information
4. Repeat if needed

When you have gathered enough information to fully answer the question, provide your final answer.""")
        
        user_msg = HumanMessage(content=current_prompt)
        
        response = await engine.llm.run_agent_step(
            messages=[user_msg],
            system_persona=str(system_msg.content),
            tools=None,
            mode="think"  # Use thinking mode for reasoning
        )
        
        clean_content = engine.llm.sanitize_thought_process(str(response.content))
        
        # Check if model provided final answer or wants to continue
        if "```python" in clean_content:
            # Model wants to execute code
            code = extract_code(clean_content, engine.llm)
            
            if not code:
                logger.warning("No code extracted, ending iteration")
                break
            
            logger.info(f"Executing research code ({len(code)} chars)...")
            result = engine.sandbox.execute_with_packages(code)
            
            # Strip base64 plot data if any
            import re
            result_clean = re.sub(
                r'data:image/png;base64,[A-Za-z0-9+/=]+',
                'data:image/png;base64,[BASE64_DATA_REMOVED]',
                result
            )
            
            logger.info(f"Execution result: {result_clean[:300]}...")
            
            # Add to history
            research_history.append({
                "iteration": iteration,
                "action": "code_execution",
                "code": code,
                "result": result_clean
            })
            
            # Check if model wants to continue or is done
            if "[DONE]" in clean_content or "final answer" in clean_content.lower():
                logger.info("Model indicated completion")
                break
            
            # Build continuation prompt
            current_prompt = get_continuation_prompt(
                user_input=user_input,
                research_history=research_history,
                last_result=result_clean,
                current_date=current_date
            )
            
        else:
            # No code - check if it's a final answer
            if any(phrase in clean_content.lower() for phrase in ["final answer", "in summary", "to conclude"]):
                logger.info("Model provided final answer")
                research_history.append({
                    "iteration": iteration,
                    "action": "final_answer",
                    "content": clean_content
                })
                break
            else:
                # Model is thinking/reasoning without code
                logger.info("Model reasoning without code, prompting for action...")
                research_history.append({
                    "iteration": iteration,
                    "action": "reasoning",
                    "content": clean_content
                })
                
                current_prompt = f"""You said:
{clean_content}

Now, either:
1. Write Python code to take the next research step (search, scrape, analyze)
2. Provide your final answer if you have enough information

What's your next action?"""
    
    # Synthesis: Create final response
    if research_history:
        last_step = research_history[-1]
        
        if last_step["action"] == "final_answer":
            final_response = last_step["content"]
        else:
            # Synthesize all findings
            logger.info("Synthesizing research findings...")
            
            synthesis_prompt = f"""Original question: {user_input}

Research conducted:
"""
            for step in research_history:
                synthesis_prompt += f"\nStep {step['iteration']}:"
                if step['action'] == 'code_execution':
                    synthesis_prompt += f"\n  Action: Executed code\n  Result: {step['result'][:500]}\n"
                elif step['action'] == 'reasoning':
                    synthesis_prompt += f"\n  Thought: {step['content'][:300]}\n"
            
            synthesis_prompt += "\n\nBased on all this research, provide a comprehensive answer to the original question."
            
            synthesis_response = await engine.llm.run_agent_step(
                messages=[HumanMessage(content=synthesis_prompt)],
                system_persona="You are Jarvis. Synthesize research findings into a clear, comprehensive answer.",
                tools=None,
                mode="speed"
            )
            
            final_response = engine.llm.sanitize_thought_process(str(synthesis_response.content))
    else:
        final_response = "I was unable to gather sufficient information to answer your question."
    
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"\n⏱️  iterative_research: {elapsed:.1f}ms ({iteration} iterations)")
    
    return {
        "final_response": final_response,
        "execution_result": f"Completed {iteration} research iterations",
        "generated_code": research_history[-1].get("code", "") if research_history else "",
        "skill_approved": False
    }
