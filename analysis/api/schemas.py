from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    mongodb: str


class AnalysisStatusResponse(BaseModel):
    window_days: int
    total_in_window: int
    tracked: int
    pending_estimate: int
    by_status: dict[str, int]
    analyzed_transactions_total: int
    reviews_total: int
    confidence_threshold: float
    search_enabled: bool


class AnalysisTriggerResponse(BaseModel):
    result: dict[str, Any]


class AnalyzedTransactionResponse(BaseModel):
    analyzed_transaction_id: str
    source_transaction_id: str
    analysis_id: str
    flow_direction: str
    amount_usd: float
    original_amount: float | None = None
    original_currency: str | None = None
    category: str
    is_subscription: bool = False
    description: str
    transaction_date: str
    source_metadata: dict[str, Any] | None = None
    duration: dict[str, Any] | None = None
    confidence: float
    created_at: datetime | None = None


class NeedsAttentionItem(BaseModel):
    transaction_id: str
    attention_reason: str | None = None
    analysis_id: str | None = None
    updated_at: datetime | None = None


class RetryResponse(BaseModel):
    transaction_id: str
    reset: bool


class AnalysisReviewResponse(BaseModel):
    review_id: str
    analysis_id: str
    source_transaction_id: str
    attention_type: str
    attention_reason: str
    confidence: float | None = None
    llm_result: dict[str, Any] | None = None
    llm_response: dict[str, Any] | None = None
    validation_error: str | None = None
    search_context: dict[str, Any] | None = None
    source_metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
