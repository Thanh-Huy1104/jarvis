from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Adjust import paths if necessary based on your structure
from app.api.routes import router
from app.core.orchestrator import Orchestrator
from app.core.state import InMemorySessionStore

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager ensures that startup and shutdown
    happen in the SAME asyncio task, preventing 'anyio' errors
    with the MCP client.
    """
    # --- STARTUP PHASE ---
    print("[Main] Initializing application state...")
    app.state.session_store = InMemorySessionStore()
    app.state.audio_cache = {}
    
    # 1. Initialize Orchestrator
    app.state.orch = Orchestrator.make_default(session_store=app.state.session_store)
    
    # 2. Connect to MCP Server (The "Hands")
    if hasattr(app.state.orch, "start"):
        try:
            await app.state.orch.start()
        except Exception as e:
            print(f"[Main] Failed to start Orchestrator/MCP: {e}")
            # We don't raise here so the app can still start in "Brain only" mode if Tools fail
    
    print("[Main] Jarvis is ready.")
    
    yield  # The application runs while yielded
    
    # --- SHUTDOWN PHASE ---
    print("[Main] Shutting down...")
    
    # 3. Cleanup MCP connection
    if hasattr(app.state.orch, "stop"):
        try:
            await app.state.orch.stop()
        except RuntimeError as e:
            # IGNORE: anyio throws "Attempted to exit cancel scope" if uvicorn
            # kills the task loop before we finish cleanup.
            if "cancel scope" not in str(e):
                print(f"[Main] Runtime error during shutdown: {e}")
        except Exception as e:
            # Suppress other shutdown errors (like broken pipes) to ensure clean exit
            print(f"[Main] Error during MCP cleanup (non-critical): {e}")
        
    print("[Main] Shutdown complete.")

app = FastAPI(title="Jarvis Local", lifespan=lifespan)

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)