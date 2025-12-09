from __future__ import annotations

import json
import re
import os
from typing import Any, AsyncIterable, Dict, List, Optional

import openai
from pydantic import ValidationError

from app.domain.ports import LLMPromptPort
from app.core.config import settings
from app.core.types import ChatMessage, ToolCall, ToolDecision, ToolResult

# =============================================================================
# CONSTANTS & PROMPTS
# =============================================================================

_DEFAULT_PERSONA = (
    "You are a hyper-intelligent, human-like AI assistant. "
    "Tone: Warm, intimate, highly competent, and natural (like Samantha from 'Her'). "
    "Output: Speak in fluid, natural sentences only. No bullet points, lists, or headers. "
    "Keep it concise (1-3 sentences) and conversational."
)

_THOUGHT_INSTRUCTION = (
    "\n\nIMPORTANT: Before answering, you must briefly reason about the user's request inside <think>...</think> tags. "
    "Use this space to analyze context, decide on tone, or plan your response. "
    "The user will NOT hear what is inside these tags."
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _to_msg(m: Any) -> Dict[str, Any]:
    """
    Converts internal ChatMessage/Dict objects into OpenAI-compatible format.
    """
    if hasattr(m, "model_dump"):
        data = m.model_dump()
    elif isinstance(m, dict):
        data = m
    else:
        data = {"role": "user", "content": str(m)}

    role = data.get("role")
    content = data.get("content")

    # Mapping 'tool' to 'user' is handled in Orchestrator now, 
    # but we keep a failsafe here just in case.
    if role == "tool":
        role = "user"
        content = f"Tool Result: {content}"
    
    return {"role": role, "content": content}


# =============================================================================
# ADAPTER IMPLEMENTATION
# =============================================================================

class VllmAdapter(LLMPromptPort):
    def __init__(self) -> None:
        self._client = openai.AsyncClient(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            api_key="EMPTY",
        )
        self._model = os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct-AWQ")

    async def decide_next_step(
        self,
        *,
        user_text: str,
        history: List[ChatMessage],
        tool_schemas: List[Dict[str, Any]],
        memories: List[str],
    ) -> ToolDecision:
        print(f"[VllmAdapter] Planning next step for: '{user_text}'")
        
        # 1. Format Memories for Context
        memory_block = ""
        if memories:
            memory_block = "\nRELEVANT MEMORIES:\n" + "\n".join(f"- {m}" for m in memories) + "\n"

        # 2. Stricter Planner Prompt
        planner_system = (
            "You are the orchestration brain of Jarvis. Your job is to determine the NEXT SINGLE STEP.\n"
            "Analyze the conversation history. Look at the latest user request AND any recent tool outputs.\n"
            "You MUST output ONLY valid JSON. No Markdown. No extra text.\n\n"
            "Schema:\n"
            "{\n"
            '  "thought": "Brief reasoning: What do I know? What do I need next?",\n'
            '  "intent": "tool" | "chat",\n'
            '  "tool_calls": [{"name": string, "args": object}],\n'
            '  "assistant_hint": string | null\n'
            "}\n\n"
            "CRITICAL RULES:\n"
            "1. **INTENT**: If you want to use a function, `intent` MUST be the string 'tool'. Never use the tool name as the intent.\n"
            "2. **execute_python**: STDOUT ONLY. You MUST `print(...)` results.\n"
            "3. **Termination**: If you have the final answer, use `intent: chat`.\n"
        )
        
        tools_str = json.dumps(tool_schemas, ensure_ascii=False)
        messages = [{"role": "system", "content": planner_system + memory_block + "\nAvailable Tools:\n" + tools_str}]
        
        for m in history[-10:]:
            messages.append(_to_msg(m))
            
        try:
            out = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.1,
                max_tokens=500,
            )
            raw = out.choices[0].message.content.strip()
            print(f"[VllmAdapter Planner]: {raw}")

            # 3. JSON SANITIZER (Fixes Chinese punctuation crashes)
            raw = raw.replace("，", ",").replace("“", '"').replace("”", '"').replace("：", ":")

            # 4. JSON Extraction
            json_match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if json_match:
                clean_json = json_match.group(1)
                data = json.loads(clean_json)

                # --- AUTO-CORRECT INTENT ---
                # If LLM put a tool name in intent, or just messed up,
                # but specifically requested tool_calls, we force 'tool'.
                intent = data.get("intent", "").lower()
                tool_calls = data.get("tool_calls", [])

                if intent != "chat" and intent != "tool":
                    if tool_calls:
                        print(f"[VllmAdapter] Auto-correcting intent '{intent}' -> 'tool'")
                        data["intent"] = "tool"
                    else:
                        data["intent"] = "chat"
                # --------------------------------

                return ToolDecision(**data)
            else:
                print("[VllmAdapter Warning] No JSON found. Defaulting to Chat.")
                return ToolDecision(intent="chat", tool_calls=[], assistant_hint=None)

        except (json.JSONDecodeError, ValidationError) as e:
            print(f"[VllmAdapter Error] Parsing Failed: {e}")
            return ToolDecision(intent="chat", tool_calls=[], assistant_hint=None)
        except Exception as e:
            print(f"[VllmAdapter Error] LLM Call Failed: {e}")
            return ToolDecision(intent="chat", tool_calls=[], assistant_hint=None)
        
    async def stream_response(
        self,
        *,
        user_text: str,
        history: List[ChatMessage],
        system_persona: str = _DEFAULT_PERSONA,
    ) -> AsyncIterable[str]:
        """
        The 'Voice' of the agent. This runs when intent="chat".
        Note: The 'system_persona' passed here now contains the [CONTEXT] hints from the planner.
        """
        
        # 1. Enhanced Persona with Thought Instructions
        enhanced_persona = system_persona + _THOUGHT_INSTRUCTION

        messages: List[Dict[str, Any]] = [{"role": "system", "content": enhanced_persona}]
        
        # 2. Convert history
        # We assume history is already curated by the Orchestrator
        for m in history:
            messages.append(_to_msg(m))
            
        # 3. Stream Response
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=settings.llama_temperature_chat,
            stream=True,
        )

        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text