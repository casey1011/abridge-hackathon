"""App configuration loaded from environment / .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/.env — resolved absolutely so it loads regardless of cwd.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    groq_api_key: str = ""
    groq_transcribe_model: str = "whisper-large-v3-turbo"


settings = Settings()
