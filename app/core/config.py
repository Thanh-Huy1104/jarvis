from pydantic import BaseModel


class Settings(BaseModel):
    # LLM
    llama_temperature_router: float = 0.0
    llama_temperature_chat: float = 0.7

    # STT
    whisper_model: str = "small.en"  # tiny.en/base.en/small.en
    # device is chosen in adapter (cpu/cuda)

    # TTS (Kokoro)
    kokoro_model: str = "kokoro-v1.0.onnx"
    kokoro_voices: str = "voices-v1.0.json"
    kokoro_voice_name: str = "af_heart"
    kokoro_lang: str = "en-us"
    kokoro_speed: float = 1.0

    # App
    max_recent_messages: int = 10
    
    database_url: str = "postgresql+asyncpg://jarvis:jarvis_password@localhost:5432/jarvis_db"


settings = Settings()
