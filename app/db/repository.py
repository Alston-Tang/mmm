from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.bson_util import to_bson_safe
from app.db.mongo import get_database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ItemRepository:
    @staticmethod
    async def list_active() -> list[dict[str, Any]]:
        db = get_database()
        cursor = db.items.find({"status": "active"})
        return await cursor.to_list(length=None)

    @staticmethod
    async def get_by_item_id(item_id: str) -> dict[str, Any] | None:
        db = get_database()
        return await db.items.find_one({"item_id": item_id})

    @staticmethod
    async def create(
        *,
        item_id: str,
        label: str,
        access_token: str,
        institution_id: str | None = None,
        institution_name: str | None = None,
    ) -> dict[str, Any]:
        db = get_database()
        now = _utcnow()
        doc = {
            "item_id": item_id,
            "label": label,
            "access_token": access_token,
            "cursor": None,
            "institution_id": institution_id,
            "institution_name": institution_name,
            "status": "active",
            "created_at": now,
            "last_sync_at": None,
            "last_sync_error": None,
        }
        await db.items.insert_one(doc)
        return doc

    @staticmethod
    async def update_cursor(item_id: str, cursor: str | None) -> None:
        db = get_database()
        await db.items.update_one({"item_id": item_id}, {"$set": {"cursor": cursor}})

    @staticmethod
    async def mark_sync_result(
        item_id: str,
        *,
        error: str | None = None,
        institution_name: str | None = None,
    ) -> None:
        db = get_database()
        update: dict[str, Any] = {
            "last_sync_at": _utcnow(),
            "last_sync_error": error,
        }
        if institution_name:
            update["institution_name"] = institution_name
        await db.items.update_one({"item_id": item_id}, {"$set": update})

    @staticmethod
    async def deactivate(item_id: str) -> bool:
        db = get_database()
        result = await db.items.update_one(
            {"item_id": item_id},
            {"$set": {"status": "inactive", "deactivated_at": _utcnow()}},
        )
        return result.modified_count > 0


class TransactionRepository:
    @staticmethod
    async def apply_sync(
        item_id: str,
        *,
        added: list[dict[str, Any]],
        modified: list[dict[str, Any]],
        removed: list[dict[str, Any]],
    ) -> dict[str, int]:
        db = get_database()
        now = _utcnow()
        stats = {"upserted": 0, "removed": 0}

        for tx in added + modified:
            tx_id = tx.get("transaction_id")
            if not tx_id:
                continue
            await db.transactions.update_one(
                {"transaction_id": tx_id},
                {
                    "$set": {
                        "transaction_id": tx_id,
                        "item_id": item_id,
                        "account_id": tx.get("account_id"),
                        "data": to_bson_safe(tx),
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
            stats["upserted"] += 1

        for tx in removed:
            tx_id = tx.get("transaction_id")
            if not tx_id:
                continue
            await db.transactions.delete_one({"transaction_id": tx_id})
            stats["removed"] += 1

        return stats

    @staticmethod
    async def count_for_item(item_id: str) -> int:
        db = get_database()
        return await db.transactions.count_documents({"item_id": item_id})
