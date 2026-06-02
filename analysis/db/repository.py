from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from analysis.db.mongo import get_analysis_collection, get_sync_collection
from analysis.models.schemas import ProcessingStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SourceTransactionRepository:
    """Read-only access to Plaid transactions synced by the sync service."""

    @staticmethod
    async def list_in_window(
        *,
        window_days: int,
        limit: int,
        exclude_statuses: list[ProcessingStatus] | None = None,
    ) -> list[dict[str, Any]]:
        """Return source transactions within the time window that need processing."""
        transactions = get_sync_collection("transactions")
        state = get_analysis_collection("transaction_analysis_state")
        cutoff = (datetime.now(UTC).date() - timedelta(days=window_days)).isoformat()

        exclude = exclude_statuses or [ProcessingStatus.RESOLVED, ProcessingStatus.NEEDS_ATTENTION]
        exclude_ids: list[str] = []
        if exclude:
            cursor = state.find(
                {"status": {"$in": [s.value for s in exclude]}},
                {"transaction_id": 1},
            )
            exclude_ids = [doc["transaction_id"] async for doc in cursor]

        query: dict[str, Any] = {"data.date": {"$gte": cutoff}}
        if exclude_ids:
            query["transaction_id"] = {"$nin": exclude_ids}

        cursor = (
            transactions.find(query)
            .sort("data.date", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    @staticmethod
    async def get_by_ids(transaction_ids: list[str]) -> list[dict[str, Any]]:
        if not transaction_ids:
            return []
        transactions = get_sync_collection("transactions")
        cursor = transactions.find({"transaction_id": {"$in": transaction_ids}})
        return [doc async for doc in cursor]

    @staticmethod
    async def count_in_window(window_days: int) -> int:
        transactions = get_sync_collection("transactions")
        cutoff = (datetime.now(UTC).date() - timedelta(days=window_days)).isoformat()
        return await transactions.count_documents({"data.date": {"$gte": cutoff}})


class AnalysisStateRepository:
    @staticmethod
    async def get(transaction_id: str) -> dict[str, Any] | None:
        return await get_analysis_collection("transaction_analysis_state").find_one(
            {"transaction_id": transaction_id},
        )

    @staticmethod
    async def upsert(
        transaction_id: str,
        *,
        status: ProcessingStatus,
        analyzed_transaction_ids: list[str] | None = None,
        analysis_id: str | None = None,
        confidence: float | None = None,
        attention_reason: str | None = None,
        user_comment: str | None = None,
        clear_user_comment: bool = False,
    ) -> None:
        now = _utcnow()
        update: dict[str, Any] = {
            "transaction_id": transaction_id,
            "status": status.value,
            "updated_at": now,
        }
        unset: dict[str, str] = {}
        if analyzed_transaction_ids is not None:
            update["analyzed_transaction_ids"] = analyzed_transaction_ids
        if analysis_id is not None:
            update["analysis_id"] = analysis_id
        if confidence is not None:
            update["confidence"] = confidence
        if attention_reason is not None:
            update["attention_reason"] = attention_reason
        if user_comment is not None:
            update["user_comment"] = user_comment
        if clear_user_comment:
            unset["user_comment"] = ""
        if status in (ProcessingStatus.RESOLVED, ProcessingStatus.NEEDS_ATTENTION):
            update["processed_at"] = now
        if status == ProcessingStatus.PENDING_RETRY:
            update["processed_at"] = None
            unset["attention_reason"] = ""
            unset["analyzed_transaction_ids"] = ""
            unset["analysis_id"] = ""
            unset["confidence"] = ""

        state = get_analysis_collection("transaction_analysis_state")
        update_doc: dict[str, Any] = {"$set": update}
        if unset:
            update_doc["$unset"] = unset
        await state.update_one(
            {"transaction_id": transaction_id},
            update_doc,
            upsert=True,
        )

    @staticmethod
    async def count_by_status() -> dict[str, int]:
        state = get_analysis_collection("transaction_analysis_state")
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        result: dict[str, int] = {
            ProcessingStatus.PENDING.value: 0,
            ProcessingStatus.RESOLVED.value: 0,
            ProcessingStatus.NEEDS_ATTENTION.value: 0,
            ProcessingStatus.PENDING_RETRY.value: 0,
        }
        async for doc in state.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    @staticmethod
    async def list_needs_attention(limit: int = 100) -> list[dict[str, Any]]:
        cursor = (
            get_analysis_collection("transaction_analysis_state")
            .find({"status": ProcessingStatus.NEEDS_ATTENTION.value})
            .sort("updated_at", -1)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    @staticmethod
    async def reset_for_retry(transaction_id: str) -> bool:
        result = await get_analysis_collection("transaction_analysis_state").delete_one(
            {"transaction_id": transaction_id, "status": ProcessingStatus.NEEDS_ATTENTION.value},
        )
        return result.deleted_count > 0

    @staticmethod
    async def get_user_comments(transaction_ids: list[str]) -> dict[str, str]:
        if not transaction_ids:
            return {}
        state = get_analysis_collection("transaction_analysis_state")
        cursor = state.find(
            {
                "transaction_id": {"$in": transaction_ids},
                "status": ProcessingStatus.PENDING_RETRY.value,
                "user_comment": {"$exists": True, "$ne": ""},
            },
            {"transaction_id": 1, "user_comment": 1},
        )
        return {
            doc["transaction_id"]: doc["user_comment"]
            async for doc in cursor
            if doc.get("user_comment")
        }

    @staticmethod
    async def queue_for_retry(transaction_id: str, comment: str) -> None:
        await AnalysisStateRepository.upsert(
            transaction_id,
            status=ProcessingStatus.PENDING_RETRY,
            user_comment=comment.strip(),
        )


class AnalyzedTransactionRepository:
    @staticmethod
    async def insert_many(docs: list[dict[str, Any]]) -> None:
        if not docs:
            return
        await get_analysis_collection("analyzed_transactions").insert_many(docs)

    @staticmethod
    async def list_recent(limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            get_analysis_collection("analyzed_transactions")
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    @staticmethod
    async def get_by_source_id(transaction_id: str) -> list[dict[str, Any]]:
        coll = get_analysis_collection("analyzed_transactions")
        cursor = coll.find(
            {"$or": [
                {"source_transaction_id": transaction_id},
                {"source_transaction_ids": transaction_id},
            ]},
        ).sort("created_at", -1)
        return [doc async for doc in cursor]

    @staticmethod
    async def count() -> int:
        return await get_analysis_collection("analyzed_transactions").count_documents({})

    @staticmethod
    async def delete_by_source_id(transaction_id: str) -> int:
        result = await get_analysis_collection("analyzed_transactions").delete_many(
            {"$or": [
                {"source_transaction_id": transaction_id},
                {"source_transaction_ids": transaction_id},
            ]},
        )
        return result.deleted_count


class AnalysisReviewRepository:
    """Stores LLM output for transactions flagged needs_attention."""

    @staticmethod
    async def insert(doc: dict[str, Any]) -> None:
        await get_analysis_collection("analysis_reviews").insert_one(doc)

    @staticmethod
    async def list_recent(limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            get_analysis_collection("analysis_reviews")
            .find()
            .sort("created_at", -1)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    @staticmethod
    async def get_by_review_id(review_id: str) -> dict[str, Any] | None:
        return await get_analysis_collection("analysis_reviews").find_one({"review_id": review_id})

    @staticmethod
    async def get_by_source_id(transaction_id: str) -> list[dict[str, Any]]:
        coll = get_analysis_collection("analysis_reviews")
        cursor = coll.find(
            {"$or": [
                {"source_transaction_id": transaction_id},
                {"source_transaction_ids": transaction_id},
            ]},
        ).sort("created_at", -1)
        return [doc async for doc in cursor]

    @staticmethod
    async def get_by_analysis_id(analysis_id: str) -> dict[str, Any] | None:
        coll = get_analysis_collection("analysis_reviews")
        return await coll.find_one(
            {"$or": [{"analysis_id": analysis_id}, {"group_id": analysis_id}]},
        )

    @staticmethod
    async def count() -> int:
        return await get_analysis_collection("analysis_reviews").count_documents({})
