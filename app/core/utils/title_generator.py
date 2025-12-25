from app.domain.ports import LLMPromptPort
from app.prompts.title_generation import get_title_generation_prompt
from langchain_core.messages import HumanMessage
import logging

logger = logging.getLogger(__name__)

async def generate_session_title(llm: LLMPromptPort, user_message: str) -> str:
    try:
        prompt = get_title_generation_prompt(user_message)
        response = await llm.run_agent_step(
            messages=[HumanMessage(content=prompt)],
            system_persona="You are a title generator.",
            tools=None,
            mode="speed"
        )
        title = str(response.content).strip().replace('"', '').replace('\n', '')
        # Truncate if too long
        if len(title) > 50:
            title = title[:47] + "..."
        return title
    except Exception as e:
        logger.error(f"Failed to generate session title: {e}")
        return "New Chat"
