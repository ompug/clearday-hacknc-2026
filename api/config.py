"""Settings loaded from api/.env (gitignored). Secrets are SecretStr so they never print or log."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    nessie_api_key: SecretStr = SecretStr("")
    nessie_base_url: str = "https://prod-api.nessieisreal.com"
    # The model (Gemma) behind an OpenAI-compatible chat-completions endpoint with tool calling.
    # Empty base URL or model: the assistant uses its template fallback only.
    llm_base_url: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = 20.0  # whole-request budget across all model calls
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = ""
    session_secret: SecretStr = SecretStr("")
    # True behind HTTPS (deploy); False for http://localhost.
    session_cookie_secure: bool = False
    # Persona-picker login under /api/dev. Turn off in production.
    enable_dev_routes: bool = True
    # Background Nessie sync (retries failed pop mirrors): seconds between runs; 0 turns it off.
    nessie_sync_interval_s: float = 60.0
    # Seconds between re-checks of connected sockets against their session or device token; 0 turns it off.
    socket_recheck_interval_s: float = 30.0

    # "local" uses DATABASE_URL_LOCAL (docker-compose TimescaleDB); "tiger" uses DATABASE_URL (Tiger Cloud).
    db_target: Literal["local", "tiger"] = "local"
    database_url: SecretStr = SecretStr("")
    database_url_local: SecretStr = SecretStr("postgresql://postgres:postgres@localhost:5432/clearday")

    web_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    @property
    def dsn(self) -> str:
        url = self.database_url if self.db_target == "tiger" else self.database_url_local
        return url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
