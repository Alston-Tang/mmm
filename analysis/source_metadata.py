from __future__ import annotations

from typing import Any


def source_metadata_from_transaction(tx: dict[str, Any]) -> dict[str, Any]:
    """Extract human-readable fields from a synced Plaid transaction."""
    data = tx.get("data") or {}
    metadata: dict[str, Any] = {
        "date": data.get("date"),
        "authorized_date": data.get("authorized_date"),
        "datetime": data.get("datetime"),
        "authorized_datetime": data.get("authorized_datetime"),
        "amount": data.get("amount"),
        "name": data.get("name"),
        "merchant_name": data.get("merchant_name"),
        "original_description": data.get("original_description"),
        "iso_currency_code": data.get("iso_currency_code"),
        "payment_channel": data.get("payment_channel"),
        "pending": data.get("pending"),
        "account_display_name": tx.get("account_display_name"),
        "account_name": tx.get("account_name"),
        "account_type": tx.get("account_type"),
        "account_subtype": tx.get("account_subtype"),
        "account_mask": tx.get("account_mask"),
        "item_label": tx.get("item_label"),
        "personal_finance_category": data.get("personal_finance_category"),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def source_transaction_date(tx: dict[str, Any]) -> str | None:
    """Preferred display date from the source transaction."""
    data = tx.get("data") or {}
    date = data.get("date")
    return str(date) if date else None
