from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import warnings
import logging
import os
from app.db.session import init_db
from app.adapters.chat_postgres import ChatPostgresAdapter

# Load environment variables from .env file
load_dotenv()

# Phoenix & OpenTelemetry Instrumentation
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Configure Phoenix
PHOENIX_HOST = os.getenv("PHOENIX_HOST", "localhost")
PHOENIX_PORT = os.getenv("PHOENIX_PORT", "6006")
PHOENIX_ENDPOINT = f"http://{PHOENIX_HOST}:{PHOENIX_PORT}/v1/traces"

# Register the tracer provider with Phoenix
tracer_provider = register(
    project_name="jarvis-agent",
    endpoint=PHOENIX_ENDPOINT,
    batch=True,
    verbose=False,
)

# Instrument LangChain
LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

# Configure logging level to show INFO logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific loggers
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("mem0").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Suppress deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.templating")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community.chat_models.openai")

from app.api.routes import router
from app.api.skills_routes import router as skills_router
from app.core.engine import JarvisEngine
from app.core.skills_engine import SkillsEngine
from app.adapters.stt_whisper import FasterWhisperAdapter
from app.core.bus import EventBus
from app.engine.runner import JobRunner

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing application state...")
    # 2. Setup Stores
    app.state.audio_cache = {}
    
    # 3. Initialize JarvisEngine (Code-First Architecture)
    app.state.engine = JarvisEngine()
    print("[Main] JarvisEngine initialized with code-first workflow")
    
    # 4. Initialize SkillsEngine (Verification Loop)
    app.state.skills_engine = SkillsEngine(
        llm=app.state.engine.llm,
        skills=app.state.engine.skills
    )
    print("[Main] SkillsEngine initialized")
    
    # 5. Initialize Event System
    app.state.event_bus = EventBus()
    app.state.job_runner = JobRunner(app.state.skills_engine, app.state.event_bus)
    print("[Main] EventBus and JobRunner initialized")
    
    # 5. Initialize Database
    await init_db()
    
    app.state.chat_history = ChatPostgresAdapter()
    
    # 6. Initialize STT (Speech-to-Text)
    try:
        app.state.stt = FasterWhisperAdapter()
        print("[Main] STT Adapter initialized (Faster Whisper)")
    except Exception as e:
        print(f"[Main] Failed to initialize STT: {e}")
        app.state.stt = None
    
    print("[Main] Jarvis is ready.")
    
    yield
    
    print("[Main] Shutting down...")

app = FastAPI(title="Jarvis Local", lifespan=lifespan)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="/ws/chat")

app.include_router(router)
app.include_router(skills_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
