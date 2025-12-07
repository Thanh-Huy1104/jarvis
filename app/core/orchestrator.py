from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import AsyncIterable, Dict, List, Optional

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

_SENT_RE = re.compile(r"^(.*?[.!?])(\s+|$)", re.DOTALL)

SYSTEM_PERSONA = (
    "You are J.A.R.V.I.S., a hyper-competent and loyal AI butler. "
    "Tone: Formal, precise, and composed. Assume the user is an expert; do not explain concepts, offer advice, or elaborate unless explicitly asked. "
    "Maintain a dry, professional demeanor at all times. "
    "Rules: "
    "1. If the user asks a follow-up question (e.g., 'What about Quebec?'), "
    "analyze the previous conversation context. If the previous turn involved a tool (like weather), "
    "you MUST use that tool again for the new entity. "
    "2. Do not guess or hallucinate real-world data like weather or prices. "
    "Output: Speak in fluid, natural sentences only. "
    "Forbidden: Do not use bullet points, lists, or headers. "
    "Keep responses extremely concise (1 sentence preferred) and strictly to the point."
)


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
                # Handle various keys Mem0 might return
                text = m.get("memory", m.get("text", m.get("content", "")))
                if text:
                    mem_texts.append(text)
                    print(f"   - Context: {text} (Score: {m.get('score', 'N/A')})")

            mem_str = "\n".join(mem_texts)
            if mem_str:
                system_prompt += f"\n\nRelevant memories:\n{mem_str}"
        else:
            print("[Memory] No relevant memories found.")

        print(f"\n[Orchestrator] FINAL SYSTEM PROMPT:\n{'-'*40}\n{system_prompt}\n{'-'*40}\n")

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
        """
        Strips markdown characters and thinking tags from text so the TTS reads it naturally.
        Example: "**Hello**" -> "Hello"
                 "<think>Hmm...</think> Hi" -> "Hi"
        """
        if not text:
            return ""
        
        # 1. Remove Thinking Blocks (<think>...</think>)
        # We use re.DOTALL to match across newlines
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. Remove Headers (### Title -> Title)
        text = re.sub(r'#+\s', '', text)
        
        # 3. Remove Links ([Google](http...) -> Google)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # 4. Remove Bold, Italic, Code, Strikethrough (*, _, `, ~)
        # We replace them with empty string
        text = re.sub(r'[\*_`~]', '', text)
        
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

        # 5. LLM Streaming
        full_text = ""
        pending = ""
        yield {"type": "assistant_start"}

        async for tok in self.llm.stream_response(
            user_text=user_text,
            history=history,
            tool_calls=decision.tool_calls,
            tool_results=tool_results,
            system_persona=system_persona_with_context,
        ):
            full_text += tok
            pending += tok
            
            # Send raw token to UI (UI can handle markdown/thinking tags if it wants)
            yield {"type": "token", "text": tok}

            # Sentence detection for TTS streaming
            while True:
                pending_stripped = pending.lstrip()
                m = _SENT_RE.match(pending_stripped)
                if not m:
                    break

                sentence = m.group(1).strip()
                pending = pending_stripped[m.end():]

                if sentence:
                    # Clean markdown AND thoughts before speaking
                    clean_sentence = self._clean_markdown(sentence)
                    
                    if clean_sentence:
                        wav = await asyncio.to_thread(self.tts.speak_wav, clean_sentence)
                        audio_id = str(uuid.uuid4())
                        audio_cache[audio_id] = wav
                        yield {"type": "audio", "audio_id": audio_id, "text": sentence}

        # Flush remaining text to TTS
        leftover = pending.strip()
        if leftover:
            clean_leftover = self._clean_markdown(leftover)
            if clean_leftover:
                wav = await asyncio.to_thread(self.tts.speak_wav, clean_leftover)
                audio_id = str(uuid.uuid4())
                audio_cache[audio_id] = wav
                yield {"type": "audio", "audio_id": audio_id, "text": leftover}

        # Finalize
        full_text = full_text.strip()
        
        # Optional: You might want to save the 'thoughts' to memory too, 
        # or strip them before saving if you only want the final answer.
        # For now, we save everything.
        await asyncio.to_thread(
            self.sessions.append, session_id, ChatMessage(role="assistant", content=full_text)
        )

        await self.save_interaction(session_id, user_text, full_text)

        yield {"type": "done", "assistant_text": full_text}