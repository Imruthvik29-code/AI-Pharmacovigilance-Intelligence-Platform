"""
Application configuration.

Loads settings from environment variables (.env locally, real env vars in
deployment). Never hardcode secrets here — see .env.example for the
expected keys.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    supabase_jwt_secret: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance so we don't re-parse the environment on every call."""
    return Settings()
