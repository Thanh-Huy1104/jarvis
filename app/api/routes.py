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
    
    engine = ws.app.state.engine
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
            
            # Handle text or audio input with JarvisEngine
            try:
                if text_input:
                    await ws.send_text(json.dumps({"type": "assistant_start"}))
                    
                    # Create callback for task status updates
                    async def task_status_callback(task_id: str, status: str):
                        await ws.send_text(json.dumps({
                            "type": "task_update",
                            "task_id": task_id,
                            "status": status
                        }))
                    
                    # Set callback on engine instance (not in state to avoid serialization issues)
                    engine._task_callback = task_status_callback
                    
                    # Build the graph and stream events
                    graph = engine.build()
                    config = {"configurable": {"thread_id": session_id}}
                    
                    execution_result_sent = False
                    done_sent = False
                    skill_data = None  # Store skill data for async saving
                    current_node = None  # Track which node is executing
                    parallel_mode = False  # Track if we're in parallel execution
                    synthesis_started = False  # Track if synthesis has been sent spacing
                    send_code = False  # Flag to control code streaming (set to False to skip code)
                    
                    # Stream the engine processing
                    async for event in graph.astream_events(
                        {
                            "user_input": text_input, 
                            "user_id": session_id
                        },
                        config=config,
                        version="v2"
                    ):
                        # Track node execution
                        if event["event"] == "on_chain_start":
                            current_node = event.get("name", "")
                            # Enter parallel mode when parallel_executor starts
                            if current_node == "parallel_executor":
                                parallel_mode = True
                        
                        # Exit parallel mode when parallel_executor ends
                        if event["event"] == "on_chain_end":
                            node_name = event.get("name", "")
                            if node_name == "parallel_executor":
                                parallel_mode = False
                        
                        # Stream partial responses from LLM (but NOT from planning/synthesis/parallel workers)
                        if event["event"] == "on_chat_model_stream":
                            chunk = event.get("data", {}).get("chunk")
                            
                            # Skip streaming during parallel execution (workers run concurrently)
                            if parallel_mode:
                                continue
                            
                            # Skip streaming from internal/backend nodes
                            if current_node in ["parallel_planner", "aggregate_parallel_results", "router"]:
                                continue
                            
                            # Skip code generation streaming if send_code is False
                            if not send_code and current_node == "think_agent":
                                continue
                            
                            # If this is the executor node streaming synthesis, send spacing first
                            if current_node == "executor" and not synthesis_started:
                                synthesis_started = True
                                await ws.send_text(json.dumps({
                                    "type": "token",
                                    "text": "\n\n"
                                }))
                            
                            if chunk and hasattr(chunk, "content") and chunk.content:
                                # Send all content including whitespace to preserve formatting
                                content = str(chunk.content)
                                await ws.send_text(json.dumps({
                                    "type": "token",
                                    "text": content
                                }))
                        
                        # Send task status updates for parallel execution
                        elif event["event"] == "on_chain_end":
                            node_name = event.get("name", "")
                            
                            # Send task queue when parallel planning completes
                            if node_name == "parallel_planner":
                                output = event.get("data", {}).get("output", {})
                                plan = output.get("plan", [])
                                if plan and len(plan) > 1:
                                    logger.info(f"Sending task queue: {len(plan)} tasks")
                                    await ws.send_text(json.dumps({
                                        "type": "task_queue",
                                        "tasks": [
                                            {
                                                "id": task["id"],
                                                "description": task["description"],
                                                "status": "queued"
                                            } for task in plan
                                        ]
                                    }))
                            
                            # Handle regular execution
                            if node_name == "executor" and not execution_result_sent:
                                output = event.get("data", {}).get("output", {})
                                # Don't send execution_result - it's already included in the synthesized final_response
                                # The final_response is streamed separately via on_chat_model_stream during synthesis
                                execution_result_sent = True
                                
                                # Capture skill data for async saving ONLY if code was executed successfully
                                # and it's not already approved (i.e., it's a new skill)
                                if not output.get("skill_approved", False):
                                    skill_data = {
                                        "name": output.get("pending_skill_name"),
                                        "code": None,  # Will get from state
                                        "description": text_input
                                    }
                                
                                # Send done immediately after execution
                                logger.info("Sending done event after execution")
                                await ws.send_text(json.dumps({"type": "done"}))
                                done_sent = True
                            elif node_name == "parallel_executor" and not execution_result_sent:
                                # Handle parallel execution results
                                output = event.get("data", {}).get("output", {})
                                final_response = output.get("final_response", "")
                                if final_response:
                                    logger.info(f"Streaming parallel results: {len(final_response)} chars")
                                    await ws.send_text(json.dumps({
                                        "type": "token",
                                        "text": final_response
                                    }))
                                    execution_result_sent = True
                                    
                                    # Send done immediately after parallel results
                                    logger.info("Sending done event after parallel execution")
                                    await ws.send_text(json.dumps({"type": "done"}))
                                    done_sent = True
                            elif node_name == "speed_agent" and not done_sent:
                                # Speed agent doesn't execute code, send done
                                logger.info("Sending done event after speed response")
                                await ws.send_text(json.dumps({"type": "done"}))
                                done_sent = True
                    
                    # Save skill and memory asynchronously in background (doesn't block UI)
                    final_state = graph.get_state(config)
                    if final_state:
                        # Synthesize and save memory for all interactions
                        async def save_synthesized_memory():
                            try:
                                from app.prompts.memory_synthesis import get_memory_synthesis_prompt
                                from langchain_core.messages import HumanMessage
                                
                                execution_result = final_state.values.get("execution_result", "")
                                final_response = final_state.values.get("final_response", "")
                                
                                # Use LLM to synthesize memory into bullet points
                                synthesis_prompt = get_memory_synthesis_prompt(
                                    user_input=str(text_input),
                                    assistant_response=final_response,
                                    execution_result=execution_result if execution_result else ""
                                )
                                
                                synthesis_response = await engine.llm.run_agent_step(
                                    messages=[HumanMessage(content=synthesis_prompt)],
                                    system_persona="You are a memory synthesizer. Create concise bullet points.",
                                    tools=None,
                                    mode="speed"
                                )
                                
                                synthesized_memory = engine.llm.sanitize_thought_process(str(synthesis_response.content))
                                
                                # Save synthesized memory
                                await engine.memory.add(
                                    text=synthesized_memory,
                                    user_id=session_id
                                )
                                logger.info(f"Saved synthesized memory: {synthesized_memory[:100]}...")
                                
                            except Exception as e:
                                logger.error(f"Failed to synthesize/save memory: {e}")
                        
                        asyncio.create_task(save_synthesized_memory())
                        
                        # Save skill only if needed
                        if skill_data and final_state.values.get("generated_code"):
                            skill_data["code"] = final_state.values["generated_code"]
                            asyncio.create_task(
                                asyncio.to_thread(
                                    engine.skills.save_skill,
                                    name=skill_data["name"],
                                    code=skill_data["code"],
                                    description=skill_data["description"]
                                )
                            )
                            logger.info(f"Saving skill '{skill_data['name']}' in background")
                    
                    # Only send done if we haven't already
                    if not done_sent:
                        logger.info("Sending final done event")
                        await ws.send_text(json.dumps({"type": "done"}))
                
                elif audio_bytes:
                    # TODO: Implement STT + engine workflow
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "error": "Audio input not yet implemented in code-first mode"
                    }))
                    
            except Exception as e:
                logger.error(f"[Engine] Error: {e}")
                import traceback
                traceback.print_exc()
                await ws.send_text(json.dumps({
                    "type": "error",
                    "error": str(e)
                }))                
    except WebSocketDisconnect:
            logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.error(f"[WS] Critical Error: {e}")
    finally:
        receiver_task.cancel()
