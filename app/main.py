from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import warnings
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging level to show INFO logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific loggers
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("app").setLevel(logging.INFO)

# Suppress deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.templating")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community.chat_models.openai")

# Observability Imports
import phoenix as px
from phoenix.otel import register

from app.api.routes import router
from app.core.engine import JarvisEngine
from app.core.state import InMemorySessionStore

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing application state...")
    
    # 1. Start Observability (The "Eye")
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
    
    # 3. Initialize JarvisEngine (Code-First Architecture)
    app.state.engine = JarvisEngine()
    print("[Main] JarvisEngine initialized with code-first workflow")
    
    print("[Main] Jarvis is ready.")
    
    yield
    
    print("[Main] Shutting down...")

app = FastAPI(title="Jarvis Local", lifespan=lifespan)

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
