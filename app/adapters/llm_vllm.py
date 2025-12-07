from __future__ import annotations

import json
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
            "You are a function calling router.\n"
            "Analyze the conversation history and the latest user request.\n"
            "You MUST output ONLY valid JSON. No Markdown. No extra text.\n"
            "Schema:\n"
            "{\n"
            '  "thought": "Step-by-step reasoning about context and intent",\n'
            '  "intent": "tool" | "chat",\n'
            '  "tool_calls": [{"name": string, "args": object}],\n'
            '  "assistant_hint": string | null\n'
            "}\n\n"
            "Rules:\n"
            "1. LOOK AT HISTORY. If the user asks a follow-up (e.g. 'and Quebec?'), apply the previous tool to the new entity.\n"
            "2. Use 'tool' if a function can help. Use 'chat' only for general conversation.\n"
            "3. Only choose tools from the provided tool list.\n"
        )
        
        tools_str = json.dumps(tool_schemas, ensure_ascii=False)
        
        messages = [{"role": "system", "content": router_system + "\nAvailable tools:\n" + tools_str}]
        
        for m in history[-5:]:
            messages.append(_to_msg(m))
            
        messages.append({"role": "user", "content": user_text})
        
        out = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.1,
        )
        
        raw = out.choices[0].message.content.strip()
        print(f"[VllmAdapter Router Thought]: {raw}")

        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            data = json.loads(raw)
            return ToolDecision(**data)
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
            tool_context += "\nTool results: " + json.dumps([_to_msg(tr) for tr in tool_results], ensure_ascii=False)

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

    # async def generate_response(
    #     self,
    #     *,
    #     user_text: str,
    #     history: List[ChatMessage],
    #     tool_calls: List[ToolCall],
    #     tool_results: List[ToolResult],
    #     system_persona: str = _DEFAULT_PERSONA,
    # ) -> str:
    #     tool_context = ""
    #     if tool_calls:
    #         tool_context += "\nTool calls: " + json.dumps([_to_msg(tc) for tc in tool_calls], ensure_ascii=False)
    #     if tool_results:
    #         tool_context += "\nTool results: " + json.dumps([_to_msg(tr) for tr in tool_results], ensure_ascii=False)

    #     enhanced_persona = system_persona + _THOUGHT_INSTRUCTION

    #     messages: List[Dict[str, Any]] = [{"role": "system", "content": enhanced_persona + tool_context}]
    #     messages += [_to_msg(m) for m in history]
    #     messages.append({"role": "user", "content": user_text})

    #     out = await self._client.chat.completions.create(
    #         model=self._model,
    #         messages=messages,
    #         temperature=settings.llama_temperature_chat,
    #         stream=False,
    #     )

    #     return out.choices[0].message.content.strip()