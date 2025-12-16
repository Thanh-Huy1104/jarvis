"""MCP (Model Context Protocol) tool execution node"""

import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.utils.code_extraction import extract_json

logger = logging.getLogger(__name__)


async def call_mcp_tools(engine, state) -> dict:
    """
    Node: Execute MCP tools for host system operations.
    Only used when tasks require host filesystem, shell, or docker access.
    """
    logger.info("="*60)
    logger.info("MCP TOOL EXECUTION")
    logger.info("="*60)
    
    try:
        # Connect to MCP servers if not already connected
        if not engine.mcp.sessions:
            logger.info("Connecting to MCP servers...")
            await engine.mcp.connect()
        
        # Get available tools
        tools = await engine.mcp.list_tools()
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
        
        response = await engine.llm.run_agent_step(
            messages=[user_msg],
            system_persona=str(system_msg.content),
            tools=None,
            mode="speed"
        )
        
        # Parse tool calls from response
        clean_response = engine.llm.sanitize_thought_process(str(response.content))
        tool_plan = extract_json(clean_response, engine.llm)
        
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
            result = await engine.mcp.call_tool(tool_name, tool_args)
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
