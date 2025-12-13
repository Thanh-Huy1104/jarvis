import json
import os
import re
import logging
import ast
from typing import List, Dict, Any
import openai
from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
)
from app.domain.ports import LLMPromptPort

logger = logging.getLogger(__name__)

class VllmAdapter(LLMPromptPort):
    def __init__(self) -> None:
        self._client = openai.AsyncClient(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            api_key="EMPTY",
        )
        self._model = os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3-14B-AWQ")

    def _convert_mcp_to_openai(self, mcp_tools: List[Dict]) -> List[Dict]:
        """Converts MCP tool definitions to OpenAI 'tools' format."""
        openai_tools = []
        for t in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("args_schema", {"type": "object", "properties": {}})
                }
            })
        return openai_tools

    def _convert_langchain_to_openai_msgs(self, messages: List[BaseMessage]) -> List[Dict]:
        """Maps LangChain message objects to OpenAI dicts."""
        openai_msgs = []
        for m in messages:
            if isinstance(m, HumanMessage):
                openai_msgs.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                msg = {"role": "assistant", "content": m.content}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"])
                            }
                        }
                        for tc in m.tool_calls
                    ]
                openai_msgs.append(msg)
            elif isinstance(m, ToolMessage):
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content
                })
            elif isinstance(m, SystemMessage):
                openai_msgs.append({"role": "system", "content": m.content})
            else:
                openai_msgs.append({"role": "user", "content": str(m.content)})
        return openai_msgs

    def _extract_tools_fallback(self, content: str) -> List[Dict]:
        """
        Fallback: If vLLM fails to parse <tool_call>, we do it manually via Regex.
        Crucial for Qwen 2.5 mixed outputs.
        """
        tools_found = []
        # Regex to find <tool_call>{JSON}</tool_call> blocks
        # We use dotall to capture newlines inside the JSON
        pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
        
        matches = pattern.findall(content)
        for match in matches:
            # Sometimes the model puts markdown json ``` inside the tag
            clean_str = match.replace("```json", "").replace("```", "").strip()
            
            data = None
            # Attempt 1: Standard JSON
            try:
                data = json.loads(clean_str)
            except json.JSONDecodeError:
                # Attempt 2: Python-style dictionary (common in local LLMs using single quotes)
                try:
                    data = ast.literal_eval(clean_str)
                except Exception:
                    pass
            
            if isinstance(data, dict):
                try:
                    tools_found.append({
                        "name": data["name"],
                        "args": data["arguments"],
                        "id": f"call_fallback_{len(tools_found)}"
                    })
                    logger.info(f"🔧 Manual Fallback Triggered: Parsed {data['name']}")
                except Exception as e:
                    logger.warning(f"Manual tool parse missing keys: {e}")
            else:
                logger.warning(f"Failed to parse manual tool call data: {clean_str[:50]}...")
        
        return tools_found

    async def run_agent_step(
        self,
        messages: List[BaseMessage],
        system_persona: str,
        tools: List[Dict[str, Any]] = None
    ) -> AIMessage:
        """
        Runs a single step of the agent using native tool calling + manual fallback.
        """
        
        openai_tools = self._convert_mcp_to_openai(tools) if tools else None
        formatted_msgs = [{"role": "system", "content": system_persona}]
        formatted_msgs.extend(self._convert_langchain_to_openai_msgs(messages))

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=formatted_msgs,
                tools=openai_tools if openai_tools else openai.NOT_GIVEN,
                tool_choice="auto" if openai_tools else openai.NOT_GIVEN,
                temperature=0.1, 
            )
            
            choice = response.choices[0].message
            content = choice.content or ""
            lc_tool_calls = []

            # 1. Try Native Parsing (vLLM)
            if choice.tool_calls:
                for tc in choice.tool_calls:
                    lc_tool_calls.append({
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments),
                        "id": tc.id or f"call_{tc.function.name}"
                    })
            
            # 2. Try Manual Fallback (If native failed but tags exist)
            if not lc_tool_calls and ("<tool_call>" in content):
                lc_tool_calls = self._extract_tools_fallback(content)
                # Clean the content so the user doesn't see raw XML tags
                content = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()

            return AIMessage(content=content, tool_calls=lc_tool_calls)

        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return AIMessage(content=f"Error generating response: {str(e)}")

    async def stream_response(
        self,
        *,
        history: List[BaseMessage],
        system_persona: str,
    ) -> Any:
        messages = [{"role": "system", "content": system_persona}]
        messages.extend(self._convert_langchain_to_openai_msgs(history))
        
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.7,
            stream=True,
        )

        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text