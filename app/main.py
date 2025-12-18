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

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
