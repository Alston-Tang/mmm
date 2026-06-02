from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from analysis.config import get_settings
from analysis.db.mongo import get_sync_collection
from analysis.source_metadata import source_transaction_date

_WECHAT_NAME_RE = re.compile(
    r"wechat|weixin|微信|tenpay|wxpay|wechatpay",
    re.IGNORECASE,
)


def plaid_text_blob(plaid_tx: dict[str, Any]) -> str:
    data = plaid_tx.get("data") or {}
    parts = [
        data.get("name"),
        data.get("merchant_name"),
        data.get("original_description"),
        plaid_tx.get("account_display_name"),
    ]
    return " ".join(str(p) for p in parts if p)


def heuristic_likely_wechat(plaid_tx: dict[str, Any]) -> bool:
    return bool(_WECHAT_NAME_RE.search(plaid_text_blob(plaid_tx)))


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _amounts_maybe_match(
    plaid_amount: float,
    wechat_amount_cny: float,
    *,
    plaid_currency: str | None,
    tolerance_ratio: float,
    usd_cny_rate: float,
) -> bool:
    plaid_abs = abs(plaid_amount)
    wechat_abs = abs(wechat_amount_cny)
    if plaid_abs <= 0 or wechat_abs <= 0:
        return True

    if plaid_currency and plaid_currency.upper() == "CNY":
        expected = plaid_abs
    else:
        expected = plaid_abs * usd_cny_rate

    delta = abs(expected - wechat_abs)
    return delta <= max(0.5, expected * tolerance_ratio)


class WeChatTransactionRepository:
    """Read-only access to WeChat transactions imported by the sync service."""

    @staticmethod
    async def find_candidates_for_plaid_transaction(
        plaid_tx: dict[str, Any],
        *,
        date_window_days: int | None = None,
        amount_tolerance_ratio: float | None = None,
        max_candidates: int | None = None,
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        window = date_window_days if date_window_days is not None else settings.wechat_date_window_days
        tolerance = (
            amount_tolerance_ratio
            if amount_tolerance_ratio is not None
            else settings.wechat_amount_tolerance_ratio
        )
        limit = max_candidates if max_candidates is not None else settings.wechat_max_candidates

        tx_date_str = source_transaction_date(plaid_tx)
        if not tx_date_str:
            return []

        center = _parse_iso_date(tx_date_str)
        if center is None:
            return []

        start = (center - timedelta(days=window)).isoformat()
        end = (center + timedelta(days=window)).isoformat()

        coll = get_sync_collection("wechat_transactions")
        cursor = coll.find(
            {"transaction_date": {"$gte": start, "$lte": end}},
            {"_id": 0},
        ).sort("transaction_time", -1)

        data = plaid_tx.get("data") or {}
        plaid_amount = float(data.get("amount") or 0)
        plaid_currency = data.get("iso_currency_code")

        candidates: list[dict[str, Any]] = []
        async for doc in cursor:
            amount = float(doc.get("amount") or 0)
            direction = (doc.get("direction") or "").strip()
            if direction and direction not in ("支出",):
                continue
            if not _amounts_maybe_match(
                plaid_amount,
                amount,
                plaid_currency=plaid_currency,
                tolerance_ratio=tolerance,
                usd_cny_rate=settings.wechat_usd_cny_rate,
            ):
                continue
            candidates.append(doc)
            if len(candidates) >= limit:
                break
        return candidates

    @staticmethod
    def simplify_for_llm(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "wechat_order_id": doc.get("wechat_order_id"),
            "transaction_time": doc.get("transaction_time"),
            "transaction_date": doc.get("transaction_date"),
            "transaction_type": doc.get("transaction_type"),
            "counterparty": doc.get("counterparty"),
            "product": doc.get("product"),
            "direction": doc.get("direction"),
            "amount_cny": doc.get("amount"),
            "payment_method": doc.get("payment_method"),
            "status": doc.get("status"),
            "remark": doc.get("remark"),
        }

    @staticmethod
    async def build_context_for_batch(
        batch: list[dict[str, Any]],
        *,
        likely_ids: set[str],
    ) -> dict[str, list[dict[str, Any]]]:
        context: dict[str, list[dict[str, Any]]] = {}
        for tx in batch:
            tx_id = tx.get("transaction_id")
            if not tx_id or tx_id not in likely_ids:
                continue
            candidates = await WeChatTransactionRepository.find_candidates_for_plaid_transaction(tx)
            if candidates:
                context[tx_id] = [
                    WeChatTransactionRepository.simplify_for_llm(doc) for doc in candidates
                ]
        return context

    @staticmethod
    async def count() -> int:
        return await get_sync_collection("wechat_transactions").count_documents({})
