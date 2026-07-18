"""App configuration loaded from environment / .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/ — resolved absolutely so env files load regardless of cwd.
_API_DIR = Path(__file__).resolve().parent.parent
# .env.local overrides .env (later files in the tuple win).
_ENV_FILES = (_API_DIR / ".env", _API_DIR / ".env.local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    groq_api_key: str = ""
    groq_transcribe_model: str = "whisper-large-v3-turbo"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"


settings = Settings()
