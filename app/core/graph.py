import asyncio
import logging
from typing import Literal

from langgraph.graph import StateGraph, END, START
from langchain_core.messages import ToolMessage, HumanMessage

from app.core.state import AgentState

logger = logging.getLogger(__name__)

class JarvisGraph:
    def __init__(self, llm, tools, memory):
        self.llm = llm
        self.tools = tools # This is the MCP Client
        self.memory = memory

        # Basic System Prompt for the ReAct Agent
        self.system_prompt = (
            "You are Jarvis, an intelligent home assistant. "
            "You have access to tools to help the user. "
            "If you need information, CALL THE TOOL. Do not hallucinate.\n"
            "If you are writing code, use the `execute_python` tool. "
            "Always print the final result in python scripts.\n"
            "Keep chat responses concise and warm."
        )

    async def agent_node(self, state: AgentState):
        """
        Decides the next action: Text Response OR Tool Call(s).
        """
        messages = state["messages"]
        
        # 1. Fetch relevant memories (Simple context injection)
        # Only search memory on the FIRST turn to avoid redundant DB hits
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
             memories = await asyncio.to_thread(
                 self.memory.search, state["user_input"], state["user_id"]
             )
             if memories:
                 # In a production app, we might insert a SystemMessage with context here
                 # For now, we rely on the memory being available in the graph state if we needed it
                 pass 

        # 2. Get available tools
        available_tools = await self.tools.list_tools()

        # 3. Invoke LLM
        response_msg = await self.llm.run_agent_step(
            messages=messages,
            system_persona=self.system_prompt,
            tools=available_tools
        )
        
        return {"messages": [response_msg]}

    async def tool_node(self, state: AgentState):
        """
        Executes tools. Handles PARALLEL calls automatically.
        """
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls
        
        # Define a wrapper to run a single tool safely
        async def run_single_tool(tc):
            try:
                logger.info(f"🛠️ Executing {tc['name']} args={tc['args']}")
                output = await self.tools.call_tool(tc['name'], tc['args'])
            except Exception as e:
                output = f"Error executing {tc['name']}: {str(e)}"
            
            return ToolMessage(
                content=output,
                tool_call_id=tc['id'],
                name=tc['name']
            )

        # Execute all tools in parallel
        if tool_calls:
            tasks = [run_single_tool(tc) for tc in tool_calls]
            results = await asyncio.gather(*tasks)
            return {"messages": results}
        return {"messages": []}

    def route_node(self, state: AgentState) -> Literal["tools", "finalize"]:
        """
        Determines if we need to loop back to tools or end.
        """
        last_message = state["messages"][-1]
        
        if last_message.tool_calls:
            return "tools"
        return "finalize"

    def build(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("agent", self.agent_node)
        workflow.add_node("tools", self.tool_node)
        
        # Entry point
        workflow.add_edge(START, "agent")
        
        # Conditional Edge: Agent -> (Tools OR End)
        workflow.add_conditional_edges(
            "agent",
            self.route_node,
            {
                "tools": "tools", 
                "finalize": END
            }
        )
        
        # Loop: Tools -> Agent (To interpret results)
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()