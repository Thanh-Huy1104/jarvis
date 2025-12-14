import json
import os
import re
import logging
import ast
from typing import List, Dict, Any

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
)
# We use the standard ChatOpenAI which emits events automatically
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    from langchain_community.chat_models import ChatOpenAI

from app.domain.ports import LLMPromptPort

logger = logging.getLogger(__name__)

class VllmAdapter(LLMPromptPort):
    def __init__(self) -> None:
        self._model = ChatOpenAI(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            api_key="EMPTY",
            model=os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3-14B-AWQ"),
            temperature=0.1,
            streaming=True # Crucial for astream_events
        )

    def _extract_tools_fallback(self, content: str) -> List[Dict]:
        """Same robust fallback logic as before."""
        tools_found = []
        
        # 1. Markdown Code Blocks
        code_block_pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
        code_matches = code_block_pattern.findall(content)
        for code in code_matches:
            tools_found.append({
                "name": "execute_python",
                "args": {"code": code.strip(), "dependencies": []},
                "id": f"call_markdown_{len(tools_found)}"
            })

        # 2. XML Tags
        xml_pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
        xml_matches = xml_pattern.findall(content)
        for match in xml_matches:
            clean_str = match.replace("```json", "").replace("```", "").strip()
            data = None
            try:
                data = json.loads(clean_str)
            except json.JSONDecodeError:
                try:
                    data = ast.literal_eval(clean_str)
                except Exception:
                    pass
            
            if isinstance(data, dict):
                tools_found.append({
                    "name": data.get("name"),
                    "args": data.get("arguments", {}),
                    "id": f"call_xml_{len(tools_found)}"
                })

        return tools_found

    def _convert_mcp_to_openai_tools(self, mcp_tools: List[Dict]) -> List[Dict]:
        """Convert to format expected by bind_tools"""
        # ChatOpenAI expects dicts or pydantic models. 
        # We manually format to OpenAI schema to be safe.
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

    async def run_agent_step(
        self,
        messages: List[BaseMessage],
        system_persona: str,
        tools: List[Dict[str, Any]] = None
    ) -> AIMessage:
        
        # Add hint for Python
        if tools:
            system_persona += (
                "\n\nIMPORTANT TOOL HINT:\n"
                "To run Python code, you can simply write a markdown block:\n"
                "```python\nprint('Hello')\n```\n"
                "This is preferred over JSON for long scripts."
            )

        # Prepend System Message
        full_messages = [SystemMessage(content=system_persona)] + messages
        
        # Bind Tools
        llm_with_tools = self._model
        if tools:
            openai_tools = self._convert_mcp_to_openai_tools(tools)
            llm_with_tools = self._model.bind_tools(openai_tools)

        try:
            # invoke() will emit events to the graph's event bus automatically
            response = await llm_with_tools.ainvoke(full_messages)
            
            # Apply Fallback Logic if no native tools found
            if not response.tool_calls:
                manual_tools = self._extract_tools_fallback(response.content)
                if manual_tools:
                    response.tool_calls = manual_tools
            
            return response

        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return AIMessage(content=f"Error generating response: {str(e)}")
