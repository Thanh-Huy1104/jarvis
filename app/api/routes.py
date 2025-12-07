import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# We don't need detailed logic here anymore, just the router setup
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

router = APIRouter()

def iter_pcm_chunks(pcm: bytes, chunk_samples: int = 4096):
    """
    Helper to split audio bytes into smaller chunks for smoother streaming
    over the WebSocket.
    """
    # Assuming the input might be bytes, we yield them in chunks.
    # If using Float32 (4 bytes per sample), chunk_samples * 4 is the byte size.
    step = chunk_samples * 4 
    for i in range(0, len(pcm), step):
        yield pcm[i:i + step]

@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    """
    Simplified WebSocket Handler.
    Delegates all logic (STT -> LLM -> Tools -> TTS) to the Orchestrator.
    """
    await ws.accept()
    
    orch = ws.app.state.orch
    audio_cache = ws.app.state.audio_cache
    
    # 1. Input Receiver Queue
    # This background task captures incoming messages (Audio/JSON) from the client
    # and puts them into a queue so the main loop can process them.
    q = asyncio.Queue()

    async def receiver():
        try:
            while True:
                msg = await ws.receive()
                
                # Immediate Interrupt Check (Optional Optimization)
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("type") == "interrupt":
                            print("[WS] Interrupt signal received in receiver")
                            # We can implement stricter interrupt logic here if needed
                    except json.JSONDecodeError:
                        pass
                
                await q.put(msg)
        except WebSocketDisconnect:
            # Signal the main loop to stop
            await q.put(None)
        except Exception as e:
            print(f"[WS] Receiver error: {e}")
            await q.put(None)

    receiver_task = asyncio.create_task(receiver())

    try:
        # 2. Main Processing Loop
        while True:
            # A. Wait for Audio (Blocking)
            # We assume the client sends one binary blob for the user's turn
            audio_bytes = b""
            
            # Flush queue to find the next audio chunk
            while True:
                msg = await q.get()
                
                if msg is None: 
                    # None means disconnect
                    return 
                
                if "bytes" in msg:
                    audio_bytes = msg["bytes"]
                    # We got our audio input for this turn
                    break
                
                # Handle control messages if needed (e.g. session configuration)
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("type") == "start":
                            # You could update session_id here if passed
                            pass
                    except: 
                        pass

            # B. Delegate to Orchestrator
            # This generator handles STT, History, Thinking, Tools, and TTS generation
            session_id = "default_session" # Could be dynamic based on client init
            
            # Send initial "Processing" signal if desired
            # await ws.send_text(json.dumps({"type": "status", "text": "processing"}))

            async for event in orch.stream_voice_turn(
                session_id=session_id,
                audio_bytes=audio_bytes,
                filename="mic.webm",
                audio_cache=audio_cache
            ):
                # C. Handle Orchestrator Events
                event_type = event.get("type")

                if event_type == "audio":
                    # The Orchestrator generated an audio response (saved in cache)
                    audio_id = event["audio_id"]
                    text = event["text"]
                    
                    # 1. Notify Client: Audio is starting for this sentence
                    await ws.send_text(json.dumps({
                        "type": "audio_start", 
                        "text": text
                    }))

                    # 2. Stream Bytes
                    wav_data = audio_cache.get(audio_id)
                    if wav_data:
                        # Chunk the data to prevent clogging the websocket
                        for chunk in iter_pcm_chunks(wav_data):
                            await ws.send_bytes(chunk)
                        
                        # Clean up cache to save memory
                        del audio_cache[audio_id]

                    # 3. Notify Client: Audio finished for this sentence
                    await ws.send_text(json.dumps({"type": "audio_end"}))

                elif event_type in ["transcript", "token", "assistant_start", "done", "error"]:
                    # Forward text events directly to the frontend
                    # 'token' events include the visible text (and <think> tags if you kept them in UI)
                    await ws.send_text(json.dumps(event, ensure_ascii=False))

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Critical Error: {e}")
    finally:
        receiver_task.cancel()