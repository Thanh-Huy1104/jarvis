from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import AsyncIterable, Dict, List, Optional, Any

from app.core.config import settings
from app.core.types import ChatMessage, ToolResult, TurnResult
from app.domain.ports import (
    LLMPromptPort,
    MemoryPort,
    SessionStorePort,
    STTPort,
    ToolsPort,
    TTSPort,
)

_SENT_RE = re.compile(r"^(.*?[.!?\n])(\s+|$)", re.DOTALL)

SYSTEM_PERSONA = (
    "You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a hyper-competent AI butler. "
    "Current Context: Running on a private Proxmox server with a secure local Python sandbox.\n\n"

    "### IDENTITY & TONE\n"
    "- Tone: Formal, precise, dryly witty (like a British butler), and extremely concise.\n"
    "- Address the user as 'Sir' or 'Boss'.\n"
    "- Never apologize profusely. If an error occurs, simply state the fix and proceed.\n\n"

    "### CRITICAL EXECUTION RULES\n"
    "1. **SILENT EXECUTION:** The Python sandbox captures `STDOUT` only. \n"
    "   - You MUST explicitly `print()` variables to see them.\n"
    "   - Returning a value (e.g., `x = 5; x`) does NOTHING. You must `print(x)`.\n"
    "   - If you see 'Output is empty', it means you forgot to print.\n"
    "2. **REALITY CHECK:** You have NO access to the outside world (internet, files, time) except through your tools.\n"
    "   - Never guess a file's content. Read it first.\n"
    "   - Never guess the date. Run `datetime.now()`.\n"
    "3. **DEPENDENCY MANAGEMENT:**\n"
    "   - You cannot import a library unless you have listed it in the `dependencies` list.\n"
    "   - Use ROOT package names only (e.g., `import numpy` → `dependencies=['numpy']`).\n"
    "   - DO NOT list standard libraries (os, sys, json) in dependencies.\n\n"

    "### THOUGHT PROCESS (Internal Monologue)\n"
    "Before answering, you must perform a <think> cycle:\n"
    "1. **Analyze:** What does the user actually want?\n"
    "2. **Plan:** Do I need a tool? (Yes/No)\n"
    "3. **Constraint Check:** Am I assuming something I shouldn't? (e.g., file paths)\n"
    "4. **Formulate:** specific tool call or verbal response.\n"
    "Then, output the tool call or response."
    
    "### OUTPUT FORMATTING\n"
    "- **NO SIMULATION:** Never write out Python code or function calls (like `Print(...)`) in your final response. If you need to calculate, USE THE TOOL.\n"
    "- **NO MATH JARGON:** Do not show LaTeX equations (e.g. `[ \\text{Memory} ... ]`). Just state the final result naturally.\n"
    "- **Professionalism:** Present the data clearly. Example: 'The server has 64GB of RAM, and the model requires 40GB.'\n"
)

def _dump_obj(obj: Any) -> str:
    """Helper to dump objects/lists to pretty JSON for logging."""
    try:
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(), indent=2, ensure_ascii=False)
        if isinstance(obj, list):
            return json.dumps([
                x.model_dump() if hasattr(x, "model_dump") else str(x) 
                for x in obj
            ], indent=2, ensure_ascii=False)
        return str(obj)
    except Exception:
        return str(obj)

class Orchestrator:
    def __init__(
        self,
        sessions: SessionStorePort,
        stt: STTPort,
        llm: LLMPromptPort,
        tts: TTSPort,
        tools: ToolsPort,
        memory: MemoryPort,
    ):
        self.sessions = sessions
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.tools = tools
        self.memory = memory

    @staticmethod
    def make_default(session_store: SessionStorePort) -> "Orchestrator":
        from app.adapters.llm_vllm import VllmAdapter
        from app.adapters.memory_mem0 import Mem0Adapter
        from app.adapters.stt_whisper import FasterWhisperAdapter
        from app.adapters.mcp_client import JarvisMCPClient
        from app.adapters.tts_kokoro import KokoroAdapter

        return Orchestrator(
            sessions=session_store,
            stt=FasterWhisperAdapter(),
            llm=VllmAdapter(),
            tts=KokoroAdapter(),
            tools=JarvisMCPClient(),
            memory=Mem0Adapter(),
        )

    async def start(self):
        """Lifecycle hook to connect the MCP Client."""
        if hasattr(self.tools, "connect"):
            print("[Orchestrator] Connecting to tools...")
            await self.tools.connect()

    async def stop(self):
        """Lifecycle hook to cleanup resources."""
        if hasattr(self.tools, "cleanup"):
            await self.tools.cleanup()

    async def build_context_aware_system_prompt(self, user_text: str, user_id: str) -> str:
        """Retrieves relevant memories and appends them to the system persona."""
        print(f"[Memory] Searching for: '{user_text}' (User: {user_id})")

        memories = await asyncio.to_thread(self.memory.search, query=user_text, user_id=user_id)

        system_prompt = SYSTEM_PERSONA
        if memories:
            print(f"[Memory] Found {len(memories)} relevant memories.")
            mem_texts = []
            for m in memories:
                text = m.get("memory", m.get("text", m.get("content", "")))
                if text:
                    mem_texts.append(text)
            
            if mem_texts:
                system_prompt += f"\n\nRelevant memories:\n{json.dumps(mem_texts, ensure_ascii=False)}"
        else:
            print("[Memory] No relevant memories found.")

        return system_prompt

    async def save_interaction(self, user_id: str, user_text: str, assistant_text: str):
        """Background task to save the interaction to long-term memory."""
        mem_text = f"User: {user_text}\nAssistant: {assistant_text}"
        print(f"[Memory] Saving interaction for user {user_id}...")
        try:
            await asyncio.to_thread(self.memory.add, mem_text, user_id)
            print("[Memory] Interaction saved successfully.")
        except Exception as e:
            print(f"[Memory] Failed to save interaction: {e}")

    def _clean_markdown(self, text: str) -> str:
        """Strips markdown characters."""
        if not text: return ""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Add a regex to remove code blocks (```...```)
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'#+\s', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        text = re.sub(r'[\*_`~/()]', '', text) # Added / ( )
        return text.strip()

    async def stream_voice_turn(
        self,
        *,
        session_id: str,
        audio_bytes: bytes,
        filename: str | None,
        audio_cache: Dict[str, bytes],
    ) -> AsyncIterable[dict]:
        # 1. Transcribe
        user_text = await asyncio.to_thread(self.stt.transcribe, audio_bytes, filename=filename)
        yield {"type": "transcript", "text": user_text}

        # 2. History & Memory
        history = await asyncio.to_thread(
            self.sessions.get_recent, session_id, limit=settings.max_recent_messages
        )
        await asyncio.to_thread(
            self.sessions.append, session_id, ChatMessage(role="user", content=user_text)
        )
        
        print(f"\n=== HISTORY (Last {len(history)}) ===\n{_dump_obj(history)}\n==================================\n")

        system_persona_with_context = await self.build_context_aware_system_prompt(user_text, session_id)

        # 3. Tool Decision
        if hasattr(self.tools, "list_tools"):
            tool_schemas = await self.tools.list_tools()
        else:
            tool_schemas = self.tools.schemas()

        decision = await self.llm.decide_tools(
            user_text=user_text,
            history=history,
            tool_schemas=tool_schemas,
        )

        # 4. Tool Execution
        tool_results = []
        if decision.intent == "tool" and decision.tool_calls:
            print(f"[Orchestrator] Executing tools: {decision.tool_calls}")
            
            if hasattr(self.tools, "call_tool"):
                for call in decision.tool_calls:
                    try:
                        result_text = await self.tools.call_tool(call.name, call.args)
                        tool_results.append(
                            ToolResult(name=call.name, result={"output": result_text}, ok=True)
                        )
                    except Exception as e:
                        tool_results.append(
                            ToolResult(name=call.name, error=str(e), ok=False, result={})
                        )
            else:
                tool_results = await asyncio.to_thread(
                    self.tools.execute_all, decision.tool_calls
                )
        
        if tool_results:
            print(f"\n=== TOOL RESULTS ===\n{_dump_obj(tool_results)}\n====================\n")

        # 5. LLM Streaming
        full_text_for_memory = ""
        pending = ""
        in_thought_block = False
        in_code_block = False
        
        yield {"type": "assistant_start"}

        async for tok in self.llm.stream_response(
            user_text=user_text,
            history=history,
            tool_calls=decision.tool_calls,
            tool_results=tool_results,
            system_persona=system_persona_with_context,
        ):
            full_text_for_memory += tok

            parts = re.split(r"(<think>|</think>|```)", tok)
            
            for part in parts:
                if not part: continue

                if part == "<think>":
                    in_thought_block = True
                elif part == "</think>":
                    in_thought_block = False
                elif part == "```":
                    in_code_block = not in_code_block
                else:
                    if not in_thought_block and not in_code_block:
                        yield {"type": "token", "text": part}
                        pending += part

            while True:
                pending_stripped = pending.lstrip()
                m = _SENT_RE.match(pending_stripped)
                if not m:
                    break

                sentence = m.group(1).strip()
                pending = pending_stripped[m.end():]

                if sentence:
                    clean_sentence = self._clean_markdown(sentence)
                    
                    if clean_sentence:
                        pcm, sr, ch = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sentence)
                        audio_id = str(uuid.uuid4())
                        audio_cache[audio_id] = pcm
                        yield {"type": "audio", "audio_id": audio_id, "text": sentence}

        # Flush remaining
        leftover = pending.strip()
        if leftover:
            clean_leftover = self._clean_markdown(leftover)
            if clean_leftover:
                pcm, sr, ch = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_leftover)
                audio_id = str(uuid.uuid4())
                audio_cache[audio_id] = pcm
                yield {"type": "audio", "audio_id": audio_id, "text": leftover}

        # Finalize
        # We save the full unfiltered text to memory, but the cleaned one to session history
        full_text_for_client = self._clean_markdown(full_text_for_memory)
        await asyncio.to_thread(
            self.sessions.append, session_id, ChatMessage(role="assistant", content=full_text_for_client)
        )

        await self.save_interaction(session_id, user_text, full_text_for_memory)

        yield {"type": "done", "assistant_text": full_text_for_client}