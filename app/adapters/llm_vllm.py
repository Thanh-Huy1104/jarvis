import os
import re
import logging
from typing import List, Dict, Any, Literal

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage
)
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    from langchain_community.chat_models import ChatOpenAI
from app.domain.ports import LLMPromptPort

logger = logging.getLogger(__name__)

class VllmAdapter(LLMPromptPort):
    def __init__(self) -> None:
        # Main model for complex reasoning (port 8000)
        self.base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        self.model_name = os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3-14B-AWQ")
        
        # Speed model for fast responses (port 8001)
        self.speed_base_url = os.getenv("VLLM_SPEED_BASE_URL", "http://localhost:8001/v1")
        self.speed_model_name = os.getenv("VLLM_SPEED_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct-AWQ")
        
        # Complex reasoning model (14B)
        self._model = ChatOpenAI(
            base_url=self.base_url,
            api_key="EMPTY",
            model=self.model_name,
            temperature=0.1,
            streaming=True,
        )
        
        # Fast response model (7B)
        self._speed_model = ChatOpenAI(
            base_url=self.speed_base_url,
            api_key="EMPTY",
            model=self.speed_model_name,
            temperature=0.3,  # Slightly higher for more natural chat
            streaming=True,
        )

    async def run_agent_step(
        self,
        messages: List[BaseMessage],
        system_persona: str,
        tools: List[Dict[str, Any]] | None = None,
        mode: Literal["speed", "think"] = "speed"
    ) -> AIMessage:
        """
        Runs one agent reasoning step with dynamic mode switching.
        
        Args:
            messages: Conversation history
            system_persona: System prompt defining agent behavior
            tools: Unused (kept for compatibility)
            mode: "speed" for fast responses, "think" for deep reasoning
            
        Returns:
            AIMessage with response
        """

        # Prepend System Message
        full_messages = [SystemMessage(content=system_persona)] + messages
        
        # Select model configuration based on mode
        if mode == "speed":
            # FAST PATH: Use 7B model on 3060 Ti (port 8001)
            llm = self._speed_model.bind(
                temperature=0.7,
                max_tokens=512
            )
            logger.info("Using SPEED mode (7B model on 3060 Ti)")
        else:
            # THINKING PATH: Use 14B model for deep reasoning (port 8000)
            llm = self._model.bind(
                temperature=0.6
            )
            logger.info("Using THINK mode (14B model)")

        try:
            # invoke() will emit events to the graph's event bus automatically
            response = await llm.ainvoke(full_messages)
            return response

        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return AIMessage(content=f"Error generating response: {str(e)}")

    async def summarize(self, user_message: str, assistant_message: str) -> str:
        """Summarize a conversation turn for memory storage."""
        system_prompt = (
            "You are a conversation summarizer. Create a concise summary of the conversation turn below. "
            "Focus on key information, decisions, and context that would be useful for future reference. "
            "Keep it brief but informative (2-3 sentences max)."
        )
        
        conversation = f"User: {user_message}\n\nAssistant: {assistant_message}"
        
        try:
            response = await self._model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=conversation)
            ])
            return str(response.content)
        except Exception as e:
            logger.error(f"Summarization Error: {e}")
            # Fallback to original format if summarization fails
            return f"User: {user_message}\nAssistant: {assistant_message}"

    def sanitize_thought_process(self, content: str) -> str:
        """
        Removes the <think> tags for the final user TTS/display.
        Reasoning models may output their chain of thought in <think></think> tags.
        This method extracts only the final answer for the user.
        
        Args:
            content: Raw LLM response potentially containing <think> tags
            
        Returns:
            Clean content with thought process removed
        """
        if not content:
            return content
            
        # Remove <think>...</think> blocks (including multiline)
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        # Also handle <thinking> variant if model uses different tags
        cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL).strip()
        
        # Clean up any excessive whitespace left behind
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        return cleaned if cleaned else content  # Fallback to original if empty
