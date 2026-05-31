"""Convert Plaid/API payloads to BSON-serializable values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_bson_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: to_bson_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_bson_safe(v) for v in value]
    if isinstance(value, tuple):
        return [to_bson_safe(v) for v in value]
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value
