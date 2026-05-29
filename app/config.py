from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Plaid
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str = "sandbox"
    plaid_days_requested: int = 90
    plaid_redirect_uri: str | None = None
    plaid_webhook_url: str | None = None

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "mmm"

    # Service
    host: str = "0.0.0.0"
    port: int = 47829
    sync_interval_seconds: int = 300
    sync_on_startup: bool = True

    @property
    def plaid_is_production(self) -> bool:
        return self.plaid_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
