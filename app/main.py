from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import warnings
import logging
import os
from app.db.session import init_db

# Load environment variables from .env file
load_dotenv()

# Configure logging level to show INFO logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific loggers
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("app").setLevel(logging.DEBUG)
logging.getLogger("mem0").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Suppress deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.templating")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community.chat_models.openai")

from app.mobile.routes import router as mobile_router
from app.adapters.stt_whisper import FasterWhisperAdapter
from app.adapters.llm_vllm import VllmAdapter

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Initializing Mobile API...")
    
    # Initialize Database
    await init_db()
    print("[Main] Database initialized")
    
    # Initialize LLM (for intent classification)
    try:
        app.state.llm = VllmAdapter()
        print("[Main] LLM initialized for intent classification")
    except Exception as e:
        print(f"[Main] Failed to initialize LLM: {e}")
        app.state.llm = None
    
    # Initialize STT (Speech-to-Text)
    try:
        app.state.stt = FasterWhisperAdapter()
        print("[Main] STT Adapter initialized (Faster Whisper)")
    except Exception as e:
        print(f"[Main] Failed to initialize STT: {e}")
        app.state.stt = None
    
    print("[Main] Mobile API ready 🚀")
    
    yield
    
    print("[Main] Shutting down...")

app = FastAPI(title="Jarvis Mobile API", lifespan=lifespan)

# Include only mobile routes
app.include_router(mobile_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)