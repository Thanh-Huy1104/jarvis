from app.core.state import AgentState
from langchain_core.messages import AIMessage
import logging


logger = logging.getLogger(__name__)

async def lint_code(engine, state: AgentState):
    
    logger.info("="*60)
    logger.info("LINTING SKILL STARTED")
    logger.info("="*60)
    
    code = state["generated_code"]
    retry_count = state.get("retry_count", 0)
    messages = state.get("messages", [])
    
    output = engine.sandbox.execute_lint(code)
    
    if output["success"]:
        return { "lint_error": None }
    else:
        error_msg = AIMessage(content=f"Linting failed. \n\nCODE:\n```python\n{code}\n```\n\nLINT ERRORS:\n```\n{output['output']}\n```\n\nPlease fix these linting issues.")
        return { 
            "lint_error": output["output"], 
            "retry_count": retry_count + 1,
            "messages": [error_msg]
        }