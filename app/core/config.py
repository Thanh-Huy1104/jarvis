from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Core settings
    database_url: str = "sqlite+aiosqlite:///./jarvis.db"

    # LLM Configuration
    vllm_base_url: str = "http://localhost:11434/v1"
    vllm_model_name: str = "llama3.1:8b"
    vllm_speed_url: str = "http://localhost:11434/v1"
    vllm_speed_model: str = "llama3.1:8b"

    # Adapters
    whisper_model: str = "base"
    kokoro_model: str = ""
    kokoro_voices: str = ""
    kokoro_voice_name: str = "en-us_ljspeech"
    kokoro_speed: float = 1.0
    kokoro_lang: str = "en"

    # Google Calendar
    google_calendar_enabled: bool = False
    google_application_credentials: Optional[str] = None
    google_oauth_credentials: Optional[str] = None

    # AWS
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_default_region: Optional[str] = None

    # Phoenix Observability
    phoenix_host: Optional[str] = None
    phoenix_port: Optional[int] = None

    # Other API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
