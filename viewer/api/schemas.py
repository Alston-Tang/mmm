from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SortField = Literal[
    "transaction_date",
    "amount_usd",
    "category",
    "confidence",
    "created_at",
    "updated_at",
]
SortOrder = Literal["asc", "desc"]
ViewKind = Literal["analyzed", "needs_attention", "pending_retry"]
ViewFilter = Literal["analyzed", "needs_attention", "pending_retry"]


class HealthResponse(BaseModel):
    status: str
    mongodb: str


class TransactionViewItem(BaseModel):
    kind: ViewKind
    source_transaction_id: str | None = None
    analyzed_transaction_id: str | None = None
    analysis_id: str | None = None
    review_id: str | None = None
    flow_direction: str | None = None
    amount_usd: float | None = None
    original_amount: float | None = None
    original_currency: str | None = None
    category: str | None = None
    is_subscription: bool = False
    description: str
    transaction_date: str | None = None
    attention_reason: str | None = None
    attention_type: str | None = None
    source_metadata: dict[str, Any] | None = None
    duration: dict[str, Any] | None = None
    confidence: float | None = None
    user_comment: str | None = None
    analysis_status: str | None = None
    pending_reanalysis: bool = False
    needs_attention: bool = False
    source_available: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnalyzedTransactionItem(TransactionViewItem):
    """Detail response for a single analyzed transaction."""

    kind: ViewKind = "analyzed"
    analyzed_transaction_id: str
    flow_direction: str
    amount_usd: float
    category: str


class TransactionListResponse(BaseModel):
    items: list[TransactionViewItem]
    total: int
    analyzed_total: int = 0
    needs_attention_total: int = 0
    pending_retry_total: int = 0
    limit: int
    offset: int
    sort_by: SortField
    sort_order: SortOrder


class FilterOptionsResponse(BaseModel):
    categories: list[str]
    flow_directions: list[str]
    sort_fields: list[str] = Field(
        default_factory=lambda: [
            "transaction_date",
            "amount_usd",
            "category",
            "confidence",
            "created_at",
            "updated_at",
        ]
    )


class RequeueRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=4000)
    source_transaction_id: str | None = None
    analyzed_transaction_id: str | None = None


class RequeueResponse(BaseModel):
    source_transaction_id: str
    status: str
    user_comment: str
    removed_analyzed_transactions: int
    review_id: str


class SourceTransactionResponse(BaseModel):
    transaction_id: str | None = None
    item_id: str | None = None
    account_id: str | None = None
    date: str | None = None
    authorized_date: str | None = None
    amount: float | None = None
    iso_currency_code: str | None = None
    name: str | None = None
    merchant_name: str | None = None
    original_description: str | None = None
    payment_channel: str | None = None
    pending: bool | None = None
    personal_finance_category: dict[str, Any] | None = None
    account_display_name: str | None = None
    account_name: str | None = None
    account_type: str | None = None
    account_subtype: str | None = None
    account_mask: str | None = None
    item_label: str | None = None
    synced_at: datetime | None = None
