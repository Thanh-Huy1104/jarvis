import asyncio
from langgraph.graph import StateGraph, END
from app.core.state import AgentState
from app.core.types import ChatMessage

class JarvisGraph:
    def __init__(self, llm, tools, memory):
        self.llm = llm
        self.tools = tools
        self.memory = memory

    async def planner_node(self, state: AgentState):
        # 1. READ MEMORY
        memories = state.get("relevant_memories", [])
        if not memories:
            memories = await asyncio.to_thread(self.memory.search, state["user_input"], state["user_id"])

        # 2. PLAN
        decision = await self.llm.decide_next_step(
            user_text=state["user_input"],
            history=state["messages"],
            tool_schemas=await self.tools.list_tools(),
            memories=memories
        )
        
        return {
            "next_step": decision.intent,
            "current_thought": decision.thought,
            "tool_call": decision.tool_calls[0].model_dump() if decision.tool_calls else None,
            "assistant_hint": decision.assistant_hint,
            "relevant_memories": memories,
            "loop_step": 1 # Increment step count
        }

    async def tool_node(self, state: AgentState):
        tool = state["tool_call"]
        
        # Log Intent
        thought_msg = ChatMessage(role="assistant", content=f"Thought: {state['current_thought']}\nAction: Calling {tool['name']}...")
        
        # Execute
        try:
            res = await self.tools.call_tool(tool['name'], tool['args'])
        except Exception as e:
            res = f"Error: {e}"

        # Log Observation
        obs_msg = ChatMessage(role="user", content=f"🔎 OBSERVATION ({tool['name']}):\n{res}")
        
        return {"messages": [thought_msg, obs_msg]}

    # --- UPDATED ROUTER LOGIC ---
    def router(self, state: AgentState):
        step_count = state.get("loop_step", 0)
        
        # 1. Safety Limit: Stop if we loop more than 5 times
        if step_count > 5:
            print("[Graph] ⚠️ Max recursion reached. Forcing exit.")
            return "responder"
            
        # 2. Normal Logic
        if state["next_step"] == "tool":
            return "tools"
        
        return "responder"

    def build(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("tools", self.tool_node)
        workflow.add_node("responder", lambda x: {}) 
        
        workflow.set_entry_point("planner")
        
        workflow.add_conditional_edges(
            "planner",
            self.router, # Uses the new safe router
            {"tools": "tools", "responder": "responder"}
        )
        
        workflow.add_edge("tools", "planner")
        workflow.add_edge("responder", END)
        
        return workflow.compile()