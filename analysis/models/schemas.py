from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FlowDirection(str, Enum):
    REDUCTION = "reduction"
    ADDITION = "addition"
    TRANSFER = "transfer"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    NEEDS_ATTENTION = "needs_attention"
    PENDING_RETRY = "pending_retry"


class DurationUnit(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class TransactionDuration(BaseModel):
    value: float = Field(gt=0)
    unit: DurationUnit


class AnalyzedTransaction(BaseModel):
    """Normalized transaction produced by analysis."""

    analyzed_transaction_id: str
    source_transaction_id: str
    analysis_id: str
    flow_direction: FlowDirection
    amount_usd: float
    original_amount: float | None = None
    original_currency: str | None = None
    category: str
    is_subscription: bool = False
    description: str
    transaction_date: str
    source_metadata: dict[str, Any] | None = None
    duration: TransactionDuration | None = None
    confidence: float = Field(ge=0, le=1)
    analysis_version: str = "v1"
    llm_reasoning: str | None = None
    created_at: datetime


class TransactionAnalysisState(BaseModel):
    """Processing state for a source (Plaid) transaction."""

    transaction_id: str
    status: ProcessingStatus
    analyzed_transaction_ids: list[str] = Field(default_factory=list)
    analysis_id: str | None = None
    confidence: float | None = None
    attention_reason: str | None = None
    user_comment: str | None = None
    updated_at: datetime
    processed_at: datetime | None = None


# --- LLM structured output schemas ---


class LLMAnalyzedTransactionOutput(BaseModel):
    flow_direction: FlowDirection
    amount_usd: float
    original_amount: float | None = None
    original_currency: str | None = None
    category: str
    is_subscription: bool = False
    description: str
    transaction_date: str | None = None
    duration_value: float | None = None
    duration_unit: DurationUnit | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    reasoning: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("confidence") is None:
            out["confidence"] = 0.5
        duration = out.pop("duration", None)
        if isinstance(duration, dict):
            out.setdefault("duration_value", duration.get("value"))
            unit = duration.get("unit")
            if unit is not None:
                out.setdefault("duration_unit", unit)
        return out


class LLMSourceTransactionResult(BaseModel):
    """Analysis result for a single source transaction (1 -> 1 analyzed output)."""

    transaction_id: str
    action: Literal["create", "needs_attention"]
    attention_reason: str | None = None
    analyzed_transactions: list[LLMAnalyzedTransactionOutput] = Field(default_factory=list)
    likely_wechat_payment: bool = False
    wechat_detection_reason: str | None = None


class LLMAnalysisResponse(BaseModel):
    results: list[LLMSourceTransactionResult]


class AttentionType(str, Enum):
    LLM_FLAGGED = "llm_flagged"
    LOW_CONFIDENCE = "low_confidence"
    VALIDATION_FAILED = "validation_failed"
    USER_FEEDBACK = "user_feedback"
