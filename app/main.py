from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Observability Imports
import phoenix as px
from openinference.instrumentation.langchain import LangChainInstrumentor

from app.api.routes import router
from app.core.orchestrator import Orchestrator
from app.core.state import InMemorySessionStore # Or your DB store

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing application state...")
    
    # 1. Start Observability (The "Eye")
    # This launches the UI at http://localhost:6006
    try:
        session = px.launch_app()
        print(f"🔭 Phoenix UI active at: {session.url}")
        LangChainInstrumentor().instrument() # Hooks into LangGraph automatically
    except Exception as e:
        print(f"⚠️ Failed to launch Phoenix: {e}")

    # 2. Setup Stores
    app.state.session_store = InMemorySessionStore()
    app.state.audio_cache = {}
    
    # 3. Initialize Orchestrator
    app.state.orch = Orchestrator.make_default(session_store=app.state.session_store)
    
    if hasattr(app.state.orch, "start"):
        await app.state.orch.start()
    
    print("[Main] Jarvis is ready.")
    
    yield
    
    print("[Main] Shutting down...")
    if hasattr(app.state.orch, "stop"):
        await app.state.orch.stop()

app = FastAPI(title="Jarvis Local", lifespan=lifespan)

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
