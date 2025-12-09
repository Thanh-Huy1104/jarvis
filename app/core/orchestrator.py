from __future__ import annotations

import asyncio
import re
import uuid
import sys
from typing import AsyncIterable, Dict, Any, Optional

from app.core.graph import JarvisGraph
from app.core.types import ChatMessage 
from app.domain.ports import (
    LLMPromptPort, MemoryPort, SessionStorePort, STTPort, ToolsPort, TTSPort
)

_SENT_RE = re.compile(r"^(.*?[.!?\n])(\s+|$)", re.DOTALL)

SYSTEM_PERSONA = (
    "You are J.A.R.V.I.S., a hyper-competent AI butler.\n"
    "Tone: Formal, precise, dryly witty. Address user as 'Sir'.\n"
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
        
        self.graph_engine = JarvisGraph(llm, tools, memory)

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
        if hasattr(self.tools, "connect"): 
            print("[Orchestrator] Connecting to MCP Tools...")
            await self.tools.connect()

    async def stop(self):
        if hasattr(self.tools, "cleanup"): 
            await self.tools.cleanup()

    def _clean_markdown_for_tts(self, text: str) -> str:
        """
        Final cleanup for TTS.
        Removes markdown, headers, and ensures no 'Thought:' lines leak through.
        """
        if not text: return ""
        # Remove bold/italic
        text = re.sub(r'[\*_`]', '', text)
        # Remove headers
        text = re.sub(r'#+\s', '', text)
        # Remove links
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove internal monologue markers if they slipped through
        text = re.sub(r'(?:^|\n)(?:Planner|Thought|Action|Observation):.*', '', text, flags=re.IGNORECASE)
        return " ".join(text.split()).strip()

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
        
        # 2. Context
        recent_history = await asyncio.to_thread(self.sessions.get_recent, session_id, limit=10)
        
        initial_state = {
            "messages": recent_history + [ChatMessage(role="user", content=user_text)],
            "user_input": user_text,
            "user_id": session_id,
            "relevant_memories": []
        }

        # 3. Execute Graph
        print(f"[Orchestrator] Starting Graph for: {user_text}")
        app = self.graph_engine.build()
        final_hint = None
        
        async for event in app.astream(initial_state):
            if "planner" in event:
                thought = event["planner"].get("current_thought")
                hint = event["planner"].get("assistant_hint")
                if hint: final_hint = hint
                # Do NOT yield 'thinking' to frontend to keep it clean
                if thought: print(f"🤖 Brain: {thought}")
            
            if "tools" in event:
                 pass

        # 4. TTS Response (Filtered Stream)
        yield {"type": "assistant_start"}
        yield {"type": "audio_format", "sample_rate": 24000}
        
        full_response = ""
        
        final_prompt = SYSTEM_PERSONA
        if final_hint:
            final_prompt += f"\n\n[CONTEXT]: {final_hint}. Use this."

        # --- STREAM FILTER STATE ---
        raw_accumulator = ""
        clean_accumulator = ""
        pending_tts = ""
        
        async for chunk in self.llm.stream_response(
            user_text=user_text,
            history=[], 
            system_persona=final_prompt
        ):
            if not chunk: continue
            
            raw_accumulator += chunk
            
            # 1. Strip <think> blocks strictly
            current_clean = re.sub(r'<think>.*?</think>', '', raw_accumulator, flags=re.DOTALL)
            
            # If we are inside an open tag, wait for it to close
            if "<think>" in current_clean and "</think>" not in current_clean:
                continue
            
            # Remove partial start tags at end
            current_clean = re.sub(r'<think.*$', '', current_clean, flags=re.DOTALL)

            new_text = current_clean[len(clean_accumulator):]
            
            if new_text:
                clean_accumulator += new_text
                pending_tts += new_text
                
                yield {"type": "token", "text": new_text}
                
                # TTS Logic
                while True:
                    m = _SENT_RE.match(pending_tts.lstrip())
                    if not m: break
                    sentence = m.group(1).strip()
                    pending_tts = pending_tts[m.end():]
                    
                    clean_sent = self._clean_markdown_for_tts(sentence)
                    # FIX: Only call TTS if we actually have text left after cleaning
                    if clean_sent and len(clean_sent) > 1: 
                        try:
                            pcm, _, _ = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sent)
                            if pcm and len(pcm) > 0:
                                audio_id = str(uuid.uuid4())
                                audio_cache[audio_id] = pcm
                                yield {"type": "audio", "audio_id": audio_id, "text": sentence}
                        except Exception as e:
                            print(f"TTS Error: {e}")

        # Flush remaining
        if pending_tts.strip():
            clean_sent = self._clean_markdown_for_tts(pending_tts)
            if clean_sent and len(clean_sent) > 1:
                try:
                    pcm, _, _ = await asyncio.to_thread(self.tts.speak_pcm_f32, clean_sent)
                    if pcm and len(pcm) > 0:
                        audio_id = str(uuid.uuid4())
                        audio_cache[audio_id] = pcm
                        yield {"type": "audio", "audio_id": audio_id, "text": pending_tts.strip()}
                except Exception: pass

        yield {"type": "done", "assistant_text": clean_accumulator}

        # 5. Save Interaction (Clean text only)
        await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="user", content=user_text))
        await asyncio.to_thread(self.sessions.append, session_id, ChatMessage(role="assistant", content=clean_accumulator))
        await asyncio.to_thread(self.memory.add, f"User: {user_text}\nAssistant: {clean_accumulator}", user_id=session_id)