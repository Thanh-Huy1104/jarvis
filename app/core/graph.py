import asyncio
import logging
from typing import Literal
from datetime import datetime

from langgraph.graph import StateGraph, END, START
from langchain_core.messages import ToolMessage

from app.core.state import AgentState

logger = logging.getLogger(__name__)

class JarvisGraph:
    def __init__(self, llm, tools, memory):
        self.llm = llm
        self.tools = tools
        self.memory = memory
        
        current_date = datetime.now().strftime("%B %d, %Y")
        
        self.system_prompt = (
            f"You are Jarvis, an intelligent assistant with real-time access to tools.\n\n"
            f"CURRENT DATE: {current_date}\n"
            f"You have access to current information through web search tools.\n\n"
            "CRITICAL RULES:\n"
            "1. When asked for current/recent information, news, or updates - USE search_web or search_news IMMEDIATELY\n"
            "2. DO NOT speculate or make up information - call the appropriate tool\n"
            "3. For web searches: use search_web (general) or search_news (recent news)\n"
            "4. For code execution: use execute_python\n"
            "5. For file operations: use read_file, write_file, list_directory\n"
            "6. For documentation/articles: use scrape_website with the URL\n\n"
            "Keep responses concise and natural. Think step-by-step but ACT with tools."
        )

    async def agent_node(self, state: AgentState):
        messages = state["messages"]
        system_persona = self.system_prompt
        
        try:
            memories = await asyncio.to_thread(
                self.memory.search, state["user_input"], state["user_id"]
            )
            if memories:
                system_persona += "\n\nRelevant Memories:\n" + "\n".join(f"- {m}" for m in memories)
        except Exception as e:
            logger.error(f"Failed to fetch memories: {e}")

        available_tools = await self.tools.list_tools()

        response_msg = await self.llm.run_agent_step(
            messages=messages,
            system_persona=system_persona,
            tools=available_tools
        )
        
        return {"messages": [response_msg]}

    async def tool_node(self, state: AgentState):
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls
        
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

        if tool_calls:
            tasks = [run_single_tool(tc) for tc in tool_calls]
            results = await asyncio.gather(*tasks)
            return {"messages": results}
        return {"messages": []}

    def route_node(self, state: AgentState) -> Literal["tools", "finalize"]:
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return "finalize"

    def build(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", self.agent_node)
        workflow.add_node("tools", self.tool_node)
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", self.route_node, {"tools": "tools", "finalize": END})
        workflow.add_edge("tools", "agent")
        return workflow.compile()