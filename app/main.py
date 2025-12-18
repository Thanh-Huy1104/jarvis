from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import warnings
import logging
import os

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
from app.core.engine import JarvisEngine

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing application state...")
    # 2. Setup Stores
    app.state.audio_cache = {}
    
    # 3. Initialize JarvisEngine (Code-First Architecture)
    app.state.engine = JarvisEngine()
    print("[Main] JarvisEngine initialized with code-first workflow")
    
    print("[Main] Jarvis is ready.")
    
    yield
    
    print("[Main] Shutting down...")

app = FastAPI(title="Jarvis Local", lifespan=lifespan)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="/ws/voice")

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
