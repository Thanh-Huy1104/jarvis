import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

router = APIRouter()

def iter_pcm_chunks(pcm: bytes, chunk_samples: int = 4096):
    """Helper to split audio bytes into smaller chunks for smoother streaming."""
    step = chunk_samples * 4 
    for i in range(0, len(pcm), step):
        yield pcm[i:i + step]

@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    """WebSocket handler for voice and text interaction."""
    await ws.accept()
    
    orch = ws.app.state.orch
    audio_cache = ws.app.state.audio_cache
    
    # Queue for incoming messages from the client
    q = asyncio.Queue()

    async def receiver():
        try:
            while True:
                msg = await ws.receive()
                await q.put(msg)
        except WebSocketDisconnect:
            await q.put(None)
        except Exception as e:
            logger.error(f"[WS] Receiver error: {e}")
            await q.put(None)

    receiver_task = asyncio.create_task(receiver())

    try:
        while True:
            audio_bytes = b""
            text_input = None
            
            # Process queue to get the next input
            while True:
                msg = await q.get()
                
                if msg is None: 
                    return 
                
                if "bytes" in msg:
                    audio_bytes = msg["bytes"]
                    break
                
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("type") == "start":
                            pass # Session configuration could be handled here
                        elif data.get("type") == "text_input":
                            text_input = data.get("text")
                            if text_input:
                                break
                    except json.JSONDecodeError:
                        logger.warning(f"Received malformed JSON on websocket: {msg['text']}")
                    except Exception as e:
                        logger.error(f"Error handling text message: {e}")

            session_id = "default_session"
            
            orchestrator_stream = None
            
            if audio_bytes: 
                orchestrator_stream = orch.stream_voice_turn(
                    session_id=session_id,
                    audio_bytes=audio_bytes,
                    filename="mic.webm",
                    audio_cache=audio_cache
                )
            elif text_input:
                orchestrator_stream = orch.stream_text_turn(
                    session_id=session_id,
                    user_text=text_input,
                    audio_cache=audio_cache
                )
            
            if orchestrator_stream:
                async for event in orchestrator_stream:
                    event_type = event.get("type")

                    if event_type == "audio":
                        audio_id = event["audio_id"]
                        text = event["text"]
                        
                        await ws.send_text(json.dumps({
                            "type": "audio_start", 
                            "text": text
                        }))

                        wav_data = audio_cache.get(audio_id)
                        if wav_data:
                            for chunk in iter_pcm_chunks(wav_data):
                                await ws.send_bytes(chunk)
                            del audio_cache[audio_id]

                        await ws.send_text(json.dumps({"type": "audio_end"}))

                    elif event_type in ["transcript", "token", "assistant_start", "done", "error"]:
                        await ws.send_text(json.dumps(event, ensure_ascii=False))                
    except WebSocketDisconnect:
            logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.error(f"[WS] Critical Error: {e}")
    finally:
        receiver_task.cancel()
