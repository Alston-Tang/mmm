from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LinkTokenResponse(BaseModel):
    link_token: str


class LinkExchangeRequest(BaseModel):
    public_token: str
    label: str = Field(..., min_length=1, max_length=128)


class ItemResponse(BaseModel):
    item_id: str
    label: str
    institution_name: str | None = None
    status: str
    created_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    transaction_count: int | None = None
    account_count: int | None = None


class AccountResponse(BaseModel):
    account_id: str
    item_id: str
    item_label: str | None = None
    display_name: str | None = None
    name: str | None = None
    official_name: str | None = None
    type: str | None = None
    subtype: str | None = None
    mask: str | None = None
    institution_name: str | None = None
    current_balance: float | None = None
    updated_at: datetime | None = None


class LinkExchangeResponse(BaseModel):
    item_id: str
    label: str
    message: str = "Account linked. Sync will run shortly."


class SyncTriggerResponse(BaseModel):
    results: list[dict]


class HealthResponse(BaseModel):
    status: str
    mongodb: str
