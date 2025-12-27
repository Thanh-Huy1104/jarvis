import logging
from typing import Literal
from functools import partial

# LangGraph & LangChain Imports
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

# Internal Imports
from app.core.state import AgentState
from app.core import nodes

logger = logging.getLogger(__name__)

class SkillsEngine:
    """
    Dedicated engine for skill verification and refinement.
    Separates the "loop until satisfied" logic from the main Jarvis flow.
    """
    
    def __init__(self, llm, skills):
        """
        Initialize with references to core components.
        
        Args:
            llm: VllmAdapter instance
            skills: SkillRegistry instance
        """
        self.llm = llm
        self.skills = skills
        self.checkpointer = MemorySaver()
        self._timing = {} # Required by nodes.reason_and_code/execute_code

    def check_verification_result(self, state: AgentState) -> Literal["think_agent", "__end__"]:
        """
        Conditional Edge: Verification loop.
        If execution failed, route back to think_agent.
        If succeeded, End.
        """
        execution_error = state.get("execution_error")
        retry_count = state.get("retry_count", 0)
        max_retries = 3
        
        if execution_error and retry_count < max_retries:
            logger.warning(f"⚠️  Verification failed (attempt {retry_count + 1}/{max_retries}), retrying...")
            return "think_agent"
        
        logger.info("✅ Verification succeeded (or max retries reached)")
        return END

    def build_verification_graph(self):
        """
        Builds a dedicated graph for skill verification/refinement.
        Start -> Linter -> (Fail? -> Think -> Linter)* -> (Pass -> Execute -> End)
        """
        workflow = StateGraph(AgentState)
        
        # Reuse nodes from core
        workflow.add_node("linter", partial(nodes.lint_code, self))
        workflow.add_node("executor", partial(nodes.execute_code, self))
        workflow.add_node("think_agent", partial(nodes.reason_and_code, self))
        
        # Start at linter
        workflow.add_edge(START, "linter")
        
        def check_lint(state):
            lint_error = state.get("lint_error")
            retry_count = state.get("retry_count", 0)
            max_retries = 3
            
            if lint_error:
                if retry_count < max_retries:
                    logger.warning(f"⚠️ Linting failed (attempt {retry_count}/{max_retries}), retrying...")
                    return "think_agent"
                logger.warning(f"⚠️ Linting failed max retries ({max_retries})")
                return END
            return "executor"
        
        workflow.add_conditional_edges(
            "linter", 
            check_lint, 
            {
                "think_agent": "think_agent",
                "executor": "executor",
                END: END
            }
        )

        # Loop logic for execution (functional tests)
        workflow.add_conditional_edges(
            "executor",
            self.check_verification_result,
            {
                "think_agent": "think_agent",
                END: END
            }
        )
        
        # After refinement, always re-lint to ensure new code is clean
        workflow.add_edge("think_agent", "linter")
        
        return workflow.compile(checkpointer=self.checkpointer)

    async def run_verification(self, code: str, user_input: str, thread_id: str = "verification"):
        """Runs the verification graph for a specific piece of code."""
        graph = self.build_verification_graph()
        
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = {
            "user_input": user_input,
            "generated_code": code,
            "retry_count": 0,
            "messages": [],
            "intent_mode": "complex" # To satisfy any checks
        }
        
        # Run until end
        final_state = await graph.ainvoke(initial_state, config=config)
        return final_state

    async def run_verification_stream(self, code: str, user_input: str, thread_id: str = "verification"):
        """Stream execution events for a specific piece of code."""
        graph = self.build_verification_graph()
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = {
            "user_input": user_input,
            "generated_code": code,
            "retry_count": 0,
            "messages": [],
            "intent_mode": "complex"
        }
        
        async for event in graph.astream_events(initial_state, config=config, version="v1"):
            yield event
