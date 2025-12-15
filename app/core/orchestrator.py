from __future__ import annotations

import asyncio
import re
import uuid
import logging
from typing import AsyncIterable, Dict

from app.core.graph import JarvisGraph
from app.core.state import AgentState
from app.core.types import ChatMessage
from langchain_core.messages import HumanMessage, AIMessage
from app.domain.ports import (
    LLMPromptPort, MemoryPort, SessionStorePort, STTPort, ToolsPort, TTSPort
)

logger = logging.getLogger(__name__)
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
        tts_enabled: bool = False,
    ):
        self.sessions = sessions
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.tools = tools
        self.memory = memory
        self.tts_enabled = tts_enabled

    @staticmethod
    def make_default(session_store: SessionStorePort, tts_enabled: bool = True) -> "Orchestrator":
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
            tts_enabled=tts_enabled,
        )

    async def start(self):
        if hasattr(self.tools, "connect"):
            print("[Orchestrator] Connecting to MCP Tools...")
            await self.tools.connect()

    async def stop(self):
        if hasattr(self.tools, "cleanup"):
            await self.tools.cleanup()

    def _clean_markdown_for_tts(self, text: str) -> str:
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
        lc_history = []
        for m in recent_history:
            if m.role == "user":
                lc_history.append(HumanMessage(content=m.content))
            else:
                lc_history.append(AIMessage(content=m.content))

        initial_state: AgentState = {
            "messages": lc_history + [HumanMessage(content=user_text)],
            "user_input": user_text,
            "user_id": session_id,
        }

        print(f"[Orchestrator] Starting Graph for: {user_text}")
        yield {"type": "assistant_start"}

        # 2. Build Graph
        graph_engine = JarvisGraph(self.llm, self.tools, self.memory)
        app = graph_engine.build()

        full_response_text = ""

        # 3. Stream from Event Bus
        # 'astream_events' is the Gold Standard. It exposes internal events.
        # We assume VllmAdapter uses ChatOpenAI which emits 'on_chat_model_stream'.
        try:
            async for event in app.astream_events(initial_state, version="v1"):
                event_type = event["event"]
                
                # A. Handle Tokens (Real-time Streaming)
                if event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        # Emit token to UI
                        yield {"type": "token", "text": chunk.content}
                        full_response_text += chunk.content
                
                # B. Handle Tools (Notifications)
                elif event_type == "on_tool_start":
                    # event['name'] gives the tool name
                    yield {"type": "tool_start", "tools": [event["name"]]}
                
                elif event_type == "on_tool_end":
                    yield {"type": "tool_end"}

        except Exception as e:
            logger.error(f"Graph execution error: {e}")
            yield {"type": "error", "message": str(e)}

        # 4. Post-Processing (TTS & Memory)
        if full_response_text:
            if self.tts_enabled:
                yield {"type": "audio_format", "sample_rate": 24000}
                
                spoken_text = re.sub(r'<think>.*?</think>', '', full_response_text, flags=re.DOTALL)
                spoken_text = re.sub(r'<tool_call>.*?</tool_call>', '', spoken_text, flags=re.DOTALL)
                spoken_text = re.sub(r'```.*?```', 'I have written the code.', spoken_text, flags=re.DOTALL)
                
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
                
                if pending_tts.strip():
                    clean_sent = self._clean_markdown_for_tts(pending_tts)
                    if clean_sent:
                        try:
                            pcm, _, _ = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sent)
                            if pcm:
                                audio_id = str(uuid.uuid4())
                                audio_cache[audio_id] = pcm
                                yield {"type": "audio", "audio_id": audio_id, "text": pending_tts.strip()}
                        except Exception: pass

            yield {"type": "done", "assistant_text": full_response_text}

            # Save to Memory with summarization
            await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="user", content=user_text))
            await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="assistant", content=full_response_text))
            
            # Summarize before saving to long-term memory
            summary = await self.llm.summarize(user_text, full_response_text)
            await asyncio.to_thread(self.memory.add, summary, user_id=session_id)

    # ... existing stream_voice_turn and stream_text_turn ...
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