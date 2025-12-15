from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import warnings

# Load environment variables from .env file
load_dotenv()

# Suppress Phoenix/Starlette deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.templating")

# Observability Imports
import phoenix as px
from phoenix.otel import register

from app.api.routes import router
from app.core.orchestrator import Orchestrator
from app.core.state import InMemorySessionStore # Or your DB store

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing application state...")
    
    # 1. Start Observability (The "Eye")
    # This launches the UI at http://localhost:6006
    try:
        import os
        # Clear Phoenix database if it exists to avoid GraphQL errors
        phoenix_db_path = os.path.expanduser("~/.phoenix")
        if os.path.exists(phoenix_db_path):
            import shutil
            print(f"🔧 Clearing Phoenix cache at {phoenix_db_path}")
            shutil.rmtree(phoenix_db_path, ignore_errors=True)
        
        session = px.launch_app()
        session_url = getattr(session, 'url', 'http://localhost:6006')
        print(f"🔭 Phoenix UI active at: {session_url}")
        
        # Programmatic OpenTelemetry setup
        tracer_provider = register(
            project_name="jarvis-agent",
            auto_instrument=True
        )
        
    except Exception as e:
        print(f"⚠️ Failed to launch Phoenix or OpenTelemetry: {e}")
        import traceback
        traceback.print_exc()

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
