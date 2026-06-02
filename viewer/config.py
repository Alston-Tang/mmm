from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "mmm"

    host: str = "0.0.0.0"
    port: int = 47831
    default_page_size: int = 50
    max_page_size: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
