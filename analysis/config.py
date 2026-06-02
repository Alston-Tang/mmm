from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "mmm"

    # LLM (OpenAI-compatible API)
    llm_api_key: str
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_timeout_seconds: int = 120
    llm_max_tokens: int = 16384

    # Analysis
    analysis_interval_seconds: int = 300
    analysis_on_startup: bool = True
    analysis_batch_size: int = 30
    analysis_window_days: int = 90
    confidence_threshold: float = 0.75

    # Web search (optional — enriches uncertain transactions before retry)
    search_enabled: bool = True
    search_api_key: str | None = None
    search_provider: str = "tavily"  # tavily | serper
    search_max_results: int = 3
    search_max_queries: int = 5
    search_max_concurrent: int = 3
    search_timeout_seconds: int = 15

    # WeChat Pay context (optional — enriches likely WeChat credit-card charges)
    wechat_enabled: bool = True
    wechat_date_window_days: int = 3
    wechat_amount_tolerance_ratio: float = 0.15
    wechat_usd_cny_rate: float = 7.2
    wechat_max_candidates: int = 15

    # Service
    host: str = "0.0.0.0"
    port: int = 47830


@lru_cache
def get_settings() -> Settings:
    return Settings()
