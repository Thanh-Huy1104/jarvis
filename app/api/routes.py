import asyncio
import json
import logging
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, HTTPException
from app.adapters.chat_postgres import ChatPostgresAdapter
from app.core.utils.title_generator import generate_session_title

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

router = APIRouter()

@router.get("/sessions")
async def get_sessions(request: Request, limit: int = 20, offset: int = 0):
    """Retrieve list of chat sessions."""
    return await request.app.state.chat_history.get_sessions(limit=limit, offset=offset)

@router.post("/sessions")
async def create_session(request: Request):
    """Create a new chat session."""
    session_id = await request.app.state.chat_history.create_session()
    return {"session_id": session_id}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a chat session and all its history."""
    success = await request.app.state.chat_history.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}

@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, request: Request):
    """Retrieve chat history for a session."""
    return await request.app.state.chat_history.get_history(session_id=session_id)

@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """WebSocket handler for text interaction."""
    await ws.accept()
    
    engine = ws.app.state.engine
    chat_history = ws.app.state.chat_history
    
    # Queue for incoming messages from the client
    q = asyncio.Queue()

    async def receiver():
        try:
            while True:
                msg = await ws.receive_text()
                await q.put(msg)
        except WebSocketDisconnect:
            await q.put(None)
        except Exception as e:
            logger.error(f"[WS] Receiver error: {e}")
            await q.put(None)

    receiver_task = asyncio.create_task(receiver())

    # Persistent session ID for this connection
    session_id = "default_session"

    try:
        while True:
            text_input = None
            
            # Process queue to get the next input
            msg = await q.get()
            
            if msg is None: 
                return 
            
            try:
                data = json.loads(msg)
                if data.get("type") == "start":
                    if "session_id" in data:
                        session_id = data["session_id"]
                        logger.info(f"[WS] Session ID set to: {session_id}")
                    continue
                elif data.get("type") == "text_input":
                    text_input = data.get("text")
            except json.JSONDecodeError:
                logger.warning(f"Received malformed JSON on websocket: {msg}")
                continue
            except Exception as e:
                logger.error(f"Error handling text message: {e}")
                continue

            if not text_input:
                continue

            # Handle text input with JarvisEngine
            try:
                # 1. Save User Message
                await chat_history.add_message(session_id, "user", text_input)

                # Trigger title generation if this is the first message
                async def generate_title_if_needed(sid, txt):
                    try:
                        history = await chat_history.get_history(sid, limit=2)
                        # If only 1 message (the one we just added), generate title
                        if len(history) == 1:
                            title = await generate_session_title(engine.llm, txt)
                            await chat_history.update_session_title(sid, title)
                            await ws.send_text(json.dumps({
                                "type": "session_update",
                                "session_id": sid,
                                "title": title
                            }))
                    except Exception as e:
                        logger.error(f"Title generation failed: {e}")

                asyncio.create_task(generate_title_if_needed(session_id, text_input))

                await ws.send_text(json.dumps({"type": "assistant_start"}))
                
                # Create callback for task status updates
                async def task_status_callback(task_id: str, status: str):
                    await ws.send_text(json.dumps({
                        "type": "task_update",
                        "task_id": task_id,
                        "status": status
                    }))
                
                # Set callback on engine instance
                engine._task_callback = task_status_callback
                
                # Build the graph and stream events
                graph = engine.build()
                config = {"configurable": {"thread_id": session_id}}
                
                execution_result_sent = False
                done_sent = False
                current_node = True  # Track which node is executing
                parallel_mode = False  # Track if we're in parallel execution
                synthesis_started = False  # Track if synthesis has been sent spacing
                send_code = True  # Flag to control code streaming (set to False to skip code)
                
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
                            execution_result_sent = True
                            
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
                    # 2. Save Assistant Message
                    final_response = final_state.values.get("final_response", "")
                    if final_response:
                        await chat_history.add_message(session_id, "assistant", final_response)

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
                
                # Only send done if we haven't already
                if not done_sent:
                    logger.info("Sending final done event")
                    await ws.send_text(json.dumps({"type": "done"}))
                
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
