"""Normalize Plaid account objects for MongoDB and transaction denormalization."""

from __future__ import annotations

from typing import Any


def account_summary(account: dict[str, Any]) -> dict[str, Any]:
    """Fields useful for joining transactions to human-readable accounts."""
    balances = account.get("balances") or {}
    return {
        "account_id": account.get("account_id"),
        "name": account.get("name"),
        "official_name": account.get("official_name"),
        "type": account.get("type"),
        "subtype": account.get("subtype"),
        "mask": account.get("mask"),
        "persistent_account_id": account.get("persistent_account_id"),
        "holder_category": account.get("holder_category"),
        "iso_currency_code": balances.get("iso_currency_code") or account.get("iso_currency_code"),
        "current_balance": balances.get("current"),
        "available_balance": balances.get("available"),
    }


def display_name(summary: dict[str, Any]) -> str:
    """e.g. 'Chase Total Checking ···1234'"""
    parts: list[str] = []
    name = summary.get("official_name") or summary.get("name")
    if name:
        parts.append(str(name))
    mask = summary.get("mask")
    if mask:
        parts.append(f"···{mask}")
    subtype = summary.get("subtype") or summary.get("type")
    if not parts and subtype:
        parts.append(str(subtype))
    return " ".join(parts) if parts else summary.get("account_id", "unknown")
