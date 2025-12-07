import asyncio
import json
import re
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.types import ChatMessage, ToolResult

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

router = APIRouter()

_SENT_RE = re.compile(r"^(.*?[.!?])(\s+|$)", re.DOTALL)

def iter_pcm_chunks(pcm: bytes, chunk_samples: int = 4096):
    step = chunk_samples * 4
    for i in range(0, len(pcm), step):
        yield pcm[i:i + step]

def _check_for_interrupt(q: asyncio.Queue) -> bool:
    while not q.empty():
        try:
            message = q.get_nowait()
            if message is None:
                return True
            if isinstance(message, dict) and "text" in message:
                try:
                    msg_obj = json.loads(message["text"])
                    if msg_obj.get("type") == "interrupt":
                        print("[WS] Interrupt signal received")
                        return True
                except (json.JSONDecodeError, AttributeError):
                    pass
        except asyncio.QueueEmpty:
            break
    return False

@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    print("[WS] New connection request received...")
    await ws.accept()
    print("[WS] Connection accepted.")
    
    orch = ws.app.state.orch
    q = asyncio.Queue()

    async def receiver(q: asyncio.Queue):
        try:
            while True:
                message = await ws.receive()
                await q.put(message)
        except WebSocketDisconnect:
            print("[WS] Client disconnected (in receiver)")
            await q.put(None)
        except Exception as e:
            print(f"[WS] Error in receiver: {e}")
            await q.put(None)

    receiver_task = None
    try:
        session_id = "default_session"
        filename = "mic.webm"
        announced_audio = False
        receiver_task = asyncio.create_task(receiver(q))

        while True:
            interrupted = False

            # --- RECEIVING PHASE ---
            audio_bytes = b""
            while True:
                message = await q.get()
                if message is None:
                    print("[WS] Sentinel received, closing handler.")
                    return
                
                if "bytes" in message:
                    audio_bytes = message.get("bytes") or b""
                    break
                elif "text" in message:
                    try:
                        text_data = message.get("text")
                        msg_obj = json.loads(text_data)
                        
                        if msg_obj.get("type") == "start":
                            session_id = msg_obj.get("session_id", session_id)
                            filename = msg_obj.get("filename", filename)
                            print(f"[WS] Session initialized: {session_id}")
                        elif msg_obj.get("type") == "disconnect":
                            print("[WS] Client requested disconnect")
                            await ws.close()
                            return
                        elif msg_obj.get("type") == "interrupt":
                             print("[WS] Interrupt received during idle")
                    except json.JSONDecodeError:
                        pass
            
            if not audio_bytes:
                continue

            print(f"[WS] Processing audio ({len(audio_bytes)} bytes)...")

            # --- PROCESSING PHASE ---
            user_text = await asyncio.to_thread(orch.stt.transcribe, audio_bytes, filename=filename)
            print(f"[WS] Transcribed text: '{user_text}'")
            
            await ws.send_text(json.dumps({"type": "transcript", "text": user_text}, ensure_ascii=False))

            history = await asyncio.to_thread(orch.sessions.get_recent, session_id, limit=10)
            await asyncio.to_thread(orch.sessions.append, session_id, ChatMessage(role="user", content=user_text))

            system_persona_with_context = await orch.build_context_aware_system_prompt(user_text, session_id)

            # --- UPDATED TOOL HANDLING ---
            # 1. Fetch schemas (Handle Async MCP vs Sync Legacy)
            if hasattr(orch.tools, "list_tools"):
                tool_schemas = await orch.tools.list_tools() # Must await this!
            else:
                tool_schemas = orch.tools.schemas()

            decision = await orch.llm.decide_tools(
                user_text=user_text,
                history=history,
                tool_schemas=tool_schemas,
            )

            tool_results = []
            if decision.intent == "tool" and decision.tool_calls:
                print(f"[WS] Executing tools: {decision.tool_calls}")
                
                # 2. Execute Tools (Handle Async MCP call_tool vs Sync Legacy execute_all)
                if hasattr(orch.tools, "call_tool"):
                    # MCP Path: Iterate and await each call
                    for call in decision.tool_calls:
                        try:
                            # call_tool returns a string (text output)
                            result_text = await orch.tools.call_tool(call.name, call.args)
                            tool_results.append(
                                ToolResult(name=call.name, result={"output": result_text}, ok=True)
                            )
                        except Exception as e:
                            tool_results.append(
                                ToolResult(name=call.name, error=str(e), ok=False, result={})
                            )
                else:
                    # Legacy Path: Run in thread
                    tool_results = await asyncio.to_thread(orch.tools.execute_all, decision.tool_calls)

            await ws.send_text(json.dumps({"type": "assistant_start"}))

            full_text = ""
            pending = ""

            # --- GENERATION & SENDING PHASE ---
            print("[WS] Streaming response...")
            async for tok in orch.llm.stream_response(
                user_text=user_text,
                history=history,
                tool_calls=decision.tool_calls,
                tool_results=tool_results,
                system_persona=system_persona_with_context,
            ):
                if _check_for_interrupt(q):
                    interrupted = True
                    break

                full_text += tok
                pending += tok
                await ws.send_text(json.dumps({"type": "token", "text": tok}, ensure_ascii=False))

                while True:
                    pending = pending.lstrip()
                    m = _SENT_RE.match(pending)
                    if not m:
                        break
                    
                    sentence = m.group(1).strip()
                    pending = pending[m.end():]

                    if not sentence:
                        continue

                    print(f"[WS] Speaking sentence: '{sentence}'")
                    pcm, sr, ch = await asyncio.to_thread(orch.tts.speak_pcm_f32, sentence)

                    if not announced_audio:
                        print(f"[WS] Announcing audio format: {sr}Hz, {ch}ch")
                        await ws.send_text(json.dumps({
                            "type": "audio_format", "format": "f32le",
                            "sample_rate": sr, "channels": ch,
                        }))
                        announced_audio = True

                    await ws.send_text(json.dumps({"type": "audio_start", "text": sentence}, ensure_ascii=False))
                    
                    for chunk in iter_pcm_chunks(pcm, chunk_samples=4096):
                        if _check_for_interrupt(q):
                            interrupted = True
                            break
                        await ws.send_bytes(chunk)
                    
                    if interrupted:
                        print("[WS] Interrupted during audio streaming")
                        break
                    
                    await ws.send_text(json.dumps({"type": "audio_end"}))
                
                if interrupted:
                    break

            if interrupted:
                while not q.empty():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                await ws.send_text(json.dumps({"type": "interrupt_end"}))
                print("[WS] Interrupt handling complete")
                continue

            leftover = pending.strip()
            if leftover:
                print(f"[WS] Speaking leftover: '{leftover}'")
                pcm, sr, ch = await asyncio.to_thread(orch.tts.speak_pcm_f32, leftover)
                if not announced_audio:
                    await ws.send_text(json.dumps({
                        "type": "audio_format", "format": "f32le",
                        "sample_rate": sr, "channels": ch,
                    }))
                await ws.send_text(json.dumps({"type": "audio_start", "text": leftover}, ensure_ascii=False))
                for chunk in iter_pcm_chunks(pcm, chunk_samples=4096):
                    await ws.send_bytes(chunk)
                await ws.send_text(json.dumps({"type": "audio_end"}))

            full_text = full_text.strip()
            await asyncio.to_thread(orch.sessions.append, session_id, ChatMessage(role="assistant", content=full_text))
            
            await orch.save_interaction(session_id, user_text, full_text)
            
            await ws.send_text(json.dumps({"type": "done", "assistant_text": full_text}, ensure_ascii=False))
            print("[WS] Turn complete")

    except (WebSocketDisconnect, asyncio.CancelledError):
        print("[WS] WebSocket disconnected or cancelled")
    except Exception as e:
        print(f"[WS] CRITICAL ERROR: {e}")
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False))
        except Exception:
            pass
    finally:
        if receiver_task and not receiver_task.done():
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
        print("[WS] Handler exited")