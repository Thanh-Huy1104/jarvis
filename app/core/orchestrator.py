from __future__ import annotations

import asyncio
import re
import uuid
from typing import AsyncIterable, Dict

from app.core.graph import JarvisGraph
from app.core.state import AgentState
from app.core.types import ChatMessage
from langchain_core.messages import HumanMessage, AIMessage
from app.domain.ports import (
    LLMPromptPort, MemoryPort, SessionStorePort, STTPort, ToolsPort, TTSPort
)

_SENT_RE = re.compile(r"^(.*?[.!?\n])(\s+|$)", re.DOTALL)

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
        
        self.graph_engine = JarvisGraph(llm, tools, memory)

    @staticmethod
    def make_default(session_store: SessionStorePort) -> "Orchestrator":
        # Imports inside method to avoid circular deps during initialization if any
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
        if hasattr(self.tools, "connect"):
            print("[Orchestrator] Connecting to MCP Tools...")
            await self.tools.connect()

    async def stop(self):
        if hasattr(self.tools, "cleanup"):
            await self.tools.cleanup()

    def _clean_markdown_for_tts(self, text: str) -> str:
        """
        Cleans text for Text-to-Speech.
        Removes markdown formatting like bolding, headers, and links.
        """
        if not text: return ""
        text = re.sub(r'[\*_`]', '', text)
        text = re.sub(r'#+\s', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        return " ".join(text.split()).strip()

    async def _stream_response(
        self,
        *,
        session_id: str,
        user_text: str,
        audio_cache: Dict[str, bytes],
    ) -> AsyncIterable[dict]:
        # 1. Retrieve History
        recent_history = await asyncio.to_thread(self.sessions.get_recent, session_id, limit=10)
        
        # Convert ChatMessage (Pydantic) to LangChain Messages
        # The Graph expects LangChain types now
        lc_history = []
        for m in recent_history:
            if m.role == "user":
                lc_history.append(HumanMessage(content=m.content))
            else:
                lc_history.append(AIMessage(content=m.content))

        # 2. Initialize State
        initial_state: AgentState = {
            "messages": lc_history + [HumanMessage(content=user_text)],
            "user_input": user_text,
            "user_id": session_id,
        }

        print(f"[Orchestrator] Starting Graph for: {user_text}")
        app = self.graph_engine.build()
        
        # 3. Run Graph
        # We invoke the graph to run to completion (the loop handles the steps)
        final_state = await app.ainvoke(initial_state)
        
        final_message = final_state["messages"][-1]
        assistant_text = final_message.content

        yield {"type": "assistant_start"}
        
        # --- PHASE 1: Send Full Text (including <think>) ---
        # We yield the complete text immediately so the UI can render it.
        yield {"type": "text_full", "text": assistant_text}

        # --- PHASE 2: Generate Audio (excluding <think>) ---
        yield {"type": "audio_format", "sample_rate": 24000}
        
        # Prepare text for TTS: Remove <think> blocks and tool artifacts
        spoken_text = re.sub(r'<think>.*?</think>', '', assistant_text, flags=re.DOTALL)
        spoken_text = re.sub(r'<tool_call>.*?</tool_call>', '', spoken_text, flags=re.DOTALL)
        
        pending_tts = spoken_text
        while True:
            m = _SENT_RE.match(pending_tts.lstrip())
            if not m: break
            sentence = m.group(1).strip()
            pending_tts = pending_tts[m.end():]
            
            clean_sent = self._clean_markdown_for_tts(sentence)
            if clean_sent and len(clean_sent) > 1:
                try:
                    pcm, _, _ = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sent)
                    if pcm and len(pcm) > 0:
                        audio_id = str(uuid.uuid4())
                        audio_cache[audio_id] = pcm
                        yield {"type": "audio", "audio_id": audio_id, "text": sentence}
                except Exception as e:
                    print(f"TTS Error: {e}")
        
        # Cleanup remaining text
        if pending_tts.strip():
            clean_sent = self._clean_markdown_for_tts(pending_tts)
            if clean_sent:
                try:
                    pcm, _, _ = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sent)
                    if pcm and len(pcm) > 0:
                        audio_id = str(uuid.uuid4())
                        audio_cache[audio_id] = pcm
                        yield {"type": "audio", "audio_id": audio_id, "text": pending_tts.strip()}
                except Exception: pass

        yield {"type": "done", "assistant_text": assistant_text}

        # 5. Save Memory
        await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="user", content=user_text))
        await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="assistant", content=assistant_text))
        await asyncio.to_thread(self.memory.add, f"User: {user_text}\nAssistant: {assistant_text}", user_id=session_id)

    async def stream_voice_turn(
        self,
        *,
        session_id: str,
        audio_bytes: bytes,
        filename: str | None,
        audio_cache: Dict[str, bytes],
    ) -> AsyncIterable[dict]:
        user_text = await asyncio.to_thread(self.stt.transcribe, audio_bytes, filename=filename)
        yield {"type": "transcript", "text": user_text}

        async for event in self._stream_response(
            session_id=session_id,
            user_text=user_text,
            audio_cache=audio_cache,
        ):
            yield event
        
    async def stream_text_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        audio_cache: Dict[str, bytes],
    ) -> AsyncIterable[dict]:
        async for event in self._stream_response(
            session_id=session_id,
            user_text=user_text,
            audio_cache=audio_cache,
        ):
            yield event