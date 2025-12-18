"""
Jarvis Semantic Router
----------------------
Routes user input to either "speed" or "complex" processing mode.
Uses 7B LLM for accurate intent classification.
"""

import logging
import os
from typing import Literal


from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class JarvisRouter:
    """
    Classifies user input to determine processing mode using LLM.
    - Speed Mode: Quick responses for simple queries/commands
    - Complex Mode: Deep reasoning for tasks requiring planning/coding
    """
    
    def __init__(self):
        # Use the 7B model on 3060 Ti for fast classification
        speed_base_url = os.getenv("VLLM_SPEED_BASE_URL", "http://localhost:8001/v1")
        speed_model_name = os.getenv("VLLM_SPEED_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct-AWQ")
        
        try:
            self.llm = ChatOpenAI(
                base_url=speed_base_url,
                api_key="EMPTY",
                model=speed_model_name,
                temperature=0.0,  # Deterministic classification
                max_tokens=10,    # Just need "speed" or "complex"
                streaming=False
            )
            logger.info(f"JarvisRouter initialized with {speed_model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize router: {e}")
            self.llm = None

    def classify(self, text: str, conversation_context: str = "") -> Literal["speed", "complex"]:
        """
        Decides if we need the 'Thinking Mode' or just 'Speed Mode'.
        
        Args:
            text: User input to classify
            conversation_context: Recent conversation history for context-aware routing
            
        Returns:
            Either "speed" for quick responses or "complex" for deep reasoning
        """
        if not self.llm:
            logger.warning("Router not initialized, defaulting to complex mode")
            return "complex"
        
        context_section = ""
        if conversation_context:
            context_section = f"\nRecent conversation:\n{conversation_context}\n"
        
        classification_prompt = f"""Classify this user input as either "speed" or "complex":{context_section}
SPEED: 
- Simple greetings, basic questions, personal info, short commands, casual conversation
- Follow-up clarifications that DON'T require new code ("show both", "what about X", "explain that")
Examples: "hello", "my name is John", "thank you", "both of them please", "what does that mean"

COMPLEX: 
- Tasks requiring code execution, data fetching, web searches, news queries, analysis
- Requests to change parameters, rerun simulations, generate new results
- Any request for financial news, stock data, web scraping, API calls, data analysis
Examples: "simulate 1000 coin flips", "now do 10 times only", "change the range to 50", "financial news", "search for", "get data from", "analyze this"

IMPORTANT: If user asks to fetch data, search web, get news, or modify numbers/parameters, classify as COMPLEX.

User input: "{text}"

Classification (respond with only "speed" or "complex"):"""
        
        try:
            response = self.llm.invoke(classification_prompt)
            result = response.content
            
            if "speed" in result:
                logger.info(f"Classified as SPEED: '{text[:50]}...'")
                return "speed"
            elif "complex" in result:
                logger.info(f"Classified as COMPLEX: '{text[:50]}...'")
                return "complex"
            else:
                # If unclear, default to complex for safety
                logger.warning(f"Unclear classification '{result}' for: '{text[:50]}...', defaulting to complex")
                return "complex"
            
        except Exception as e:
            logger.error(f"Router classification error: {e}, defaulting to complex")
            return "complex"

    def get_route_stats(self) -> dict:
        """Returns statistics about route configurations (for debugging)"""
        if not self.llm:
            return {"initialized": False}
        
        return {
            "model": "Qwen2.5-7B-Instruct-AWQ",
            "endpoint": "http://localhost:8001/v1",
            "initialized": True
        }