from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from viewer.db.mongo import get_collection, get_writable_collection

SortField = Literal[
    "transaction_date",
    "amount_usd",
    "category",
    "confidence",
    "created_at",
    "updated_at",
]
SortOrder = Literal["asc", "desc"]

_SORTABLE_FIELDS = frozenset({
    "transaction_date",
    "amount_usd",
    "category",
    "confidence",
    "created_at",
    "updated_at",
})

PENDING_RETRY_STATUS = "pending_retry"
NEEDS_ATTENTION_STATUS = "needs_attention"


class AnalyzedTransactionViewerRepository:
    @staticmethod
    def _build_query(
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        flow_direction: str | None = None,
        is_subscription: bool | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        min_confidence: float | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}

        if date_from or date_to:
            date_filter: dict[str, Any] = {}
            if date_from:
                date_filter["$gte"] = date_from
            if date_to:
                date_filter["$lte"] = date_to
            query["transaction_date"] = date_filter

        if category:
            query["category"] = category

        if flow_direction:
            query["flow_direction"] = flow_direction

        if is_subscription is not None:
            query["is_subscription"] = is_subscription

        if min_amount is not None or max_amount is not None:
            amount_filter: dict[str, Any] = {}
            if min_amount is not None:
                amount_filter["$gte"] = min_amount
            if max_amount is not None:
                amount_filter["$lte"] = max_amount
            query["amount_usd"] = amount_filter

        if min_confidence is not None:
            query["confidence"] = {"$gte": min_confidence}

        if q:
            escaped = re.escape(q.strip())
            if escaped:
                query["$or"] = [
                    {"description": {"$regex": escaped, "$options": "i"}},
                    {"source_metadata.name": {"$regex": escaped, "$options": "i"}},
                    {"source_metadata.merchant_name": {"$regex": escaped, "$options": "i"}},
                    {"source_metadata.account_display_name": {"$regex": escaped, "$options": "i"}},
                ]

        return query

    @staticmethod
    async def list_transactions(
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        flow_direction: str | None = None,
        is_subscription: bool | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        min_confidence: float | None = None,
        q: str | None = None,
        sort_by: SortField = "transaction_date",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if sort_by not in _SORTABLE_FIELDS:
            sort_by = "transaction_date"

        query = AnalyzedTransactionViewerRepository._build_query(
            date_from=date_from,
            date_to=date_to,
            category=category,
            flow_direction=flow_direction,
            is_subscription=is_subscription,
            min_amount=min_amount,
            max_amount=max_amount,
            min_confidence=min_confidence,
            q=q,
        )

        coll = get_collection("analyzed_transactions")
        direction = 1 if sort_order == "asc" else -1
        total = await coll.count_documents(query)
        cursor = (
            coll.find(query, {"_id": 0})
            .sort(sort_by, direction)
            .skip(offset)
            .limit(limit)
        )
        items = [doc async for doc in cursor]
        return items, total

    @staticmethod
    async def get_by_id(analyzed_transaction_id: str) -> dict[str, Any] | None:
        return await get_collection("analyzed_transactions").find_one(
            {"analyzed_transaction_id": analyzed_transaction_id},
            {"_id": 0},
        )

    @staticmethod
    async def distinct_categories() -> list[str]:
        values = await get_collection("analyzed_transactions").distinct("category")
        return sorted(v for v in values if v)

    @staticmethod
    async def distinct_flow_directions() -> list[str]:
        values = await get_collection("analyzed_transactions").distinct("flow_direction")
        return sorted(v for v in values if v)


class NeedsAttentionViewerRepository:
    @staticmethod
    def _review_sort_date(doc: dict[str, Any]) -> str:
        meta = doc.get("source_metadata") or {}
        data = meta.get("data") or {}
        return data.get("date") or doc.get("created_at", "")

    @staticmethod
    async def list_needs_attention(
        *,
        q: str | None = None,
        sort_by: SortField = "transaction_date",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        state_coll = get_collection("transaction_analysis_state")
        review_coll = get_collection("analysis_reviews")

        state_cursor = state_coll.find({"status": NEEDS_ATTENTION_STATUS})
        states = [doc async for doc in state_cursor]
        if not states:
            return [], 0

        tx_ids = [s["transaction_id"] for s in states]
        state_by_tx = {s["transaction_id"]: s for s in states}

        review_cursor = review_coll.find({"source_transaction_id": {"$in": tx_ids}})
        reviews_by_tx: dict[str, dict[str, Any]] = {}
        async for review in review_cursor:
            tx_id = review.get("source_transaction_id")
            if not tx_id:
                continue
            existing = reviews_by_tx.get(tx_id)
            if existing is None or review.get("created_at", "") > existing.get("created_at", ""):
                reviews_by_tx[tx_id] = review

        items: list[dict[str, Any]] = []
        for tx_id in tx_ids:
            state = state_by_tx[tx_id]
            review = reviews_by_tx.get(tx_id)
            meta = (review or {}).get("source_metadata") or {}
            amount = meta.get("amount")
            if amount is None:
                amount = (meta.get("data") or {}).get("amount")
            description = (
                (review or {}).get("attention_reason")
                or state.get("attention_reason")
                or meta.get("name")
                or (meta.get("data") or {}).get("name")
                or "Needs attention"
            )
            tx_date = meta.get("date") or (meta.get("data") or {}).get("date")
            item = {
                "kind": "needs_attention",
                "source_transaction_id": tx_id,
                "review_id": (review or {}).get("review_id"),
                "analysis_id": state.get("analysis_id") or (review or {}).get("analysis_id"),
                "attention_reason": state.get("attention_reason") or (review or {}).get("attention_reason"),
                "attention_type": (review or {}).get("attention_type"),
                "confidence": state.get("confidence") or (review or {}).get("confidence"),
                "transaction_date": tx_date,
                "amount_usd": abs(float(amount)) if amount is not None else None,
                "description": description,
                "source_metadata": meta or None,
                "updated_at": state.get("updated_at"),
                "created_at": (review or {}).get("created_at"),
            }
            items.append(item)

        if q:
            escaped = re.escape(q.strip()).lower()
            if escaped:
                items = [
                    item
                    for item in items
                    if escaped in (item.get("description") or "").lower()
                    or escaped in ((item.get("source_metadata") or {}).get("name") or "").lower()
                    or escaped in ((item.get("source_metadata") or {}).get("merchant_name") or "").lower()
                    or escaped in ((item.get("source_metadata") or {}).get("account_display_name") or "").lower()
                ]

        reverse = sort_order == "desc"
        if sort_by == "updated_at":
            items.sort(key=lambda i: i.get("updated_at") or "", reverse=reverse)
        elif sort_by == "amount_usd":
            items.sort(key=lambda i: i.get("amount_usd") or 0, reverse=reverse)
        elif sort_by == "confidence":
            items.sort(key=lambda i: i.get("confidence") or 0, reverse=reverse)
        else:
            items.sort(
                key=lambda i: i.get("transaction_date") or "",
                reverse=reverse,
            )

        total = len(items)
        return items[offset : offset + limit], total

    @staticmethod
    async def count_needs_attention() -> int:
        return await get_collection("transaction_analysis_state").count_documents(
            {"status": NEEDS_ATTENTION_STATUS},
        )


class PendingRetryViewerRepository:
    @staticmethod
    def _metadata_from_source(src: dict[str, Any]) -> dict[str, Any]:
        return {
            key: src.get(key)
            for key in (
                "date",
                "authorized_date",
                "amount",
                "iso_currency_code",
                "name",
                "merchant_name",
                "original_description",
                "payment_channel",
                "pending",
                "account_display_name",
                "account_name",
                "account_type",
                "account_subtype",
                "account_mask",
                "item_label",
            )
            if src.get(key) is not None
        }

    @staticmethod
    async def list_pending_retry(
        *,
        q: str | None = None,
        sort_by: SortField = "transaction_date",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        state_coll = get_collection("transaction_analysis_state")
        states = [
            doc async for doc in state_coll.find({"status": PENDING_RETRY_STATUS})
        ]
        if not states:
            return [], 0

        tx_ids = [s["transaction_id"] for s in states]
        tx_coll = get_collection("transactions")
        tx_cursor = tx_coll.find({"transaction_id": {"$in": tx_ids}}, {"_id": 0})
        tx_by_id = {
            doc["transaction_id"]: SourceTransactionViewerRepository._format(doc)
            async for doc in tx_cursor
        }

        items: list[dict[str, Any]] = []
        for state in states:
            tx_id = state["transaction_id"]
            src = tx_by_id.get(tx_id) or {}
            amount = src.get("amount")
            comment = (state.get("user_comment") or "").strip()
            description = (
                src.get("merchant_name")
                or src.get("name")
                or comment
                or "Pending re-analysis"
            )
            items.append({
                "kind": "pending_retry",
                "source_transaction_id": tx_id,
                "user_comment": comment,
                "updated_at": state.get("updated_at"),
                "transaction_date": src.get("date"),
                "amount_usd": abs(float(amount)) if amount is not None else None,
                "description": description,
                "source_metadata": PendingRetryViewerRepository._metadata_from_source(src) or None,
                "pending_reanalysis": True,
                "analysis_status": PENDING_RETRY_STATUS,
            })

        if q:
            escaped = re.escape(q.strip()).lower()
            if escaped:
                items = [
                    item
                    for item in items
                    if escaped in (item.get("description") or "").lower()
                    or escaped in (item.get("user_comment") or "").lower()
                    or escaped in ((item.get("source_metadata") or {}).get("name") or "").lower()
                    or escaped in ((item.get("source_metadata") or {}).get("merchant_name") or "").lower()
                ]

        reverse = sort_order == "desc"
        if sort_by == "updated_at":
            items.sort(key=lambda i: i.get("updated_at") or "", reverse=reverse)
        elif sort_by == "amount_usd":
            items.sort(key=lambda i: i.get("amount_usd") or 0, reverse=reverse)
        else:
            items.sort(key=lambda i: i.get("transaction_date") or "", reverse=reverse)

        total = len(items)
        return items[offset : offset + limit], total

    @staticmethod
    async def count_pending_retry() -> int:
        return await get_collection("transaction_analysis_state").count_documents(
            {"status": PENDING_RETRY_STATUS},
        )

    @staticmethod
    async def get_status_by_source_ids(source_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not source_ids:
            return {}
        cursor = get_collection("transaction_analysis_state").find(
            {"transaction_id": {"$in": source_ids}},
            {"transaction_id": 1, "status": 1, "user_comment": 1},
        )
        return {doc["transaction_id"]: doc async for doc in cursor}


class SourceTransactionViewerRepository:
    @staticmethod
    def _format(doc: dict[str, Any]) -> dict[str, Any]:
        data = doc.get("data") or {}
        pfc = data.get("personal_finance_category") or {}
        return {
            "transaction_id": doc.get("transaction_id"),
            "item_id": doc.get("item_id"),
            "account_id": doc.get("account_id"),
            "date": data.get("date"),
            "authorized_date": data.get("authorized_date"),
            "amount": data.get("amount"),
            "iso_currency_code": data.get("iso_currency_code"),
            "name": data.get("name"),
            "merchant_name": data.get("merchant_name"),
            "original_description": data.get("original_description"),
            "payment_channel": data.get("payment_channel"),
            "pending": data.get("pending"),
            "personal_finance_category": pfc if pfc else None,
            "account_display_name": doc.get("account_display_name"),
            "account_name": doc.get("account_name"),
            "account_type": doc.get("account_type"),
            "account_subtype": doc.get("account_subtype"),
            "account_mask": doc.get("account_mask"),
            "item_label": doc.get("item_label"),
            "synced_at": doc.get("updated_at"),
        }

    @staticmethod
    async def get_by_id(transaction_id: str) -> dict[str, Any] | None:
        doc = await get_collection("transactions").find_one(
            {"transaction_id": transaction_id},
            {"_id": 0},
        )
        if not doc:
            return None
        return SourceTransactionViewerRepository._format(doc)


class TransactionFeedbackRepository:
    @staticmethod
    async def source_transaction_exists(source_transaction_id: str) -> bool:
        doc = await get_collection("transactions").find_one(
            {"transaction_id": source_transaction_id},
            {"transaction_id": 1},
        )
        return doc is not None

    @staticmethod
    async def existing_source_transaction_ids(transaction_ids: list[str]) -> set[str]:
        if not transaction_ids:
            return set()
        cursor = get_collection("transactions").find(
            {"transaction_id": {"$in": transaction_ids}},
            {"transaction_id": 1},
        )
        return {doc["transaction_id"] async for doc in cursor}

    @staticmethod
    async def resolve_source_transaction_id(
        *,
        source_transaction_id: str | None = None,
        analyzed_transaction_id: str | None = None,
    ) -> str | None:
        if source_transaction_id:
            return source_transaction_id
        if not analyzed_transaction_id:
            return None
        doc = await get_collection("analyzed_transactions").find_one(
            {"analyzed_transaction_id": analyzed_transaction_id},
            {"source_transaction_id": 1, "source_transaction_ids": 1},
        )
        if not doc:
            return None
        if doc.get("source_transaction_id"):
            return doc["source_transaction_id"]
        ids = doc.get("source_transaction_ids") or []
        return ids[0] if ids else None

    @staticmethod
    async def submit_comment(
        *,
        source_transaction_id: str,
        comment: str,
    ) -> dict[str, Any]:
        comment = comment.strip()
        if not comment:
            raise ValueError("Comment cannot be empty")
        if not await TransactionFeedbackRepository.source_transaction_exists(source_transaction_id):
            raise ValueError(
                "Source transaction no longer exists. It may have been replaced when the "
                "charge posted; re-queue the posted transaction instead.",
            )

        now = datetime.now(UTC)
        deleted = await get_writable_collection("analyzed_transactions").delete_many(
            {"$or": [
                {"source_transaction_id": source_transaction_id},
                {"source_transaction_ids": source_transaction_id},
            ]},
        )

        review_id = str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())
        review_doc = {
            "review_id": review_id,
            "analysis_id": analysis_id,
            "source_transaction_id": source_transaction_id,
            "attention_type": "user_feedback",
            "attention_reason": comment,
            "user_comment": comment,
            "created_at": now,
        }
        await get_writable_collection("analysis_reviews").insert_one(review_doc)

        state_coll = get_writable_collection("transaction_analysis_state")
        await state_coll.update_one(
            {"transaction_id": source_transaction_id},
            {
                "$set": {
                    "transaction_id": source_transaction_id,
                    "status": PENDING_RETRY_STATUS,
                    "user_comment": comment,
                    "updated_at": now,
                },
                "$unset": {
                    "attention_reason": "",
                    "analyzed_transaction_ids": "",
                    "analysis_id": "",
                    "confidence": "",
                    "processed_at": "",
                },
            },
            upsert=True,
        )

        return {
            "source_transaction_id": source_transaction_id,
            "status": PENDING_RETRY_STATUS,
            "user_comment": comment,
            "removed_analyzed_transactions": deleted.deleted_count,
            "review_id": review_id,
        }
