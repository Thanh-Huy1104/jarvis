from __future__ import annotations

import json
import re  # Added for better JSON parsing
from typing import Any, AsyncIterable, Dict, List

import openai
from pydantic import ValidationError

from app.domain.ports import LLMPromptPort
from app.core.config import settings
from app.core.types import ChatMessage, ToolCall, ToolDecision, ToolResult

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

def _to_msg(m: Any) -> Dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()
    if isinstance(m, dict):
        return {"role": m.get("role"), "content": m.get("content")}
    return {"role": "user", "content": str(m)}


class VllmAdapter(LLMPromptPort):
    def __init__(self) -> None:
        self._client = openai.AsyncClient(
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
        )
        self._model = "Qwen/Qwen2.5-7B-Instruct-AWQ"

    async def decide_tools(
        self,
        *,
        user_text: str,
        history: List[ChatMessage],
        tool_schemas: List[Dict[str, Any]],
    ) -> ToolDecision:
        print(f"[VllmAdapter] Deciding tools for user_text: '{user_text}'")
        
        router_system = (
            "You are the brain of an advanced AI system. Your job is to select the correct tool to fulfill a user request.\n"
            "You MUST output ONLY valid JSON. No Markdown formatting around it. No explanation text outside the JSON.\n\n"
            "Schema:\n"
            "{\n"
            '  "thought": "Brief reasoning: What does the user want? Do I need a tool?",\n'
            '  "intent": "tool" | "chat",\n'
            '  "tool_calls": [{"name": string, "args": object}],\n'
            '  "assistant_hint": string | null\n'
            "}\n\n"
            "CRITICAL RULES FOR TOOLS:\n"
            "1. **execute_python**:\n"
            "   - The sandbox captures STDOUT only. You MUST include `print(...)` in your code to see results.\n"
            "   - If importing libraries, you MUST list them in the `dependencies` array (e.g. ['numpy']).\n"
            "   - Use ROOT package names only (e.g. 'numpy', NOT 'numpy.linalg').\n"
            "2. **Context**:\n"
            "   - Look at the history. If the user refers to 'it' or 'that file', use the filename from the previous turn.\n"
            "3. **Efficiency**:\n"
            "   - Use 'chat' if no external data is needed (e.g., greetings, philosophical questions).\n"
        )
        
        tools_str = json.dumps(tool_schemas, ensure_ascii=False)
        
        messages = [{"role": "system", "content": router_system + "\nAvailable tools:\n" + tools_str}]
        
        # Pass recent history so the router understands context (e.g. "Run that code again")
        for m in history[-5:]:
            messages.append(_to_msg(m))
            
        messages.append({"role": "user", "content": user_text})
        
        out = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.1, # Keep low for JSON stability
        )
        
        raw = out.choices[0].message.content.strip()
        print(f"[VllmAdapter Router Thought]: {raw}")

        try:
            # --- CHANGED: More robust JSON extraction (Regex) ---
            # Finds the first { and the last } to handle markdown blocks or stray text
            json_match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if json_match:
                clean_json = json_match.group(1)
                data = json.loads(clean_json)
                return ToolDecision(**data)
            else:
                # Fallback if no JSON found
                print("[VllmAdapter Warning] No JSON found in router output.")
                return ToolDecision(intent="chat", tool_calls=[], assistant_hint=None)

        except (json.JSONDecodeError, ValidationError) as e:
            print(f"[VllmAdapter Error] Failed to parse router JSON: {e}")
            return ToolDecision(intent="chat", tool_calls=[], assistant_hint=None)

    async def stream_response(
        self,
        *,
        user_text: str,
        history: List[ChatMessage],
        tool_calls: List[ToolCall],
        tool_results: List[ToolResult],
        system_persona: str = _DEFAULT_PERSONA,
    ) -> AsyncIterable[str]:
        tool_context = ""
        if tool_calls:
            tool_context += "\nTool calls: " + json.dumps([_to_msg(tc) for tc in tool_calls], ensure_ascii=False)
        
        if tool_results:
            # --- CHANGED: Format Tool Results clearly for the LLM ---
            tool_context += "\n\n=== TOOL EXECUTION RESULTS ===\n"
            for tr in tool_results:
                # Handle potentially large outputs or errors gracefully
                content = str(tr.result.get('output', 'No Output'))
                tool_context += f"Tool '{tr.name}' output:\n{content}\n"
            tool_context += "==============================\n"

        # Inject the thought instruction into the persona
        enhanced_persona = system_persona + _THOUGHT_INSTRUCTION

        messages: List[Dict[str, Any]] = [{"role": "system", "content": enhanced_persona + tool_context}]
        messages += [_to_msg(m) for m in history]
        messages.append({"role": "user", "content": user_text})

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