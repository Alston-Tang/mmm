from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sync.db.account_fields import account_summary, display_name
from sync.db.bson_util import to_bson_safe
from sync.db.analysis_cleanup import delete_analysis_artifacts_for_transactions
from sync.db.mongo import get_database


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
    async def update_institution(
        item_id: str,
        *,
        institution_id: str | None = None,
        institution_name: str | None = None,
    ) -> None:
        db = get_database()
        update: dict[str, Any] = {}
        if institution_id:
            update["institution_id"] = institution_id
        if institution_name:
            update["institution_name"] = institution_name
        if update:
            await db.items.update_one({"item_id": item_id}, {"$set": update})

    @staticmethod
    async def mark_sync_result(
        item_id: str,
        *,
        error: str | None = None,
        institution_name: str | None = None,
        institution_id: str | None = None,
    ) -> None:
        db = get_database()
        update: dict[str, Any] = {
            "last_sync_at": _utcnow(),
            "last_sync_error": error,
        }
        if institution_name:
            update["institution_name"] = institution_name
        if institution_id:
            update["institution_id"] = institution_id
        await db.items.update_one({"item_id": item_id}, {"$set": update})

    @staticmethod
    async def deactivate(item_id: str) -> bool:
        db = get_database()
        result = await db.items.update_one(
            {"item_id": item_id},
            {"$set": {"status": "inactive", "deactivated_at": _utcnow()}},
        )
        return result.modified_count > 0


class AccountRepository:
    @staticmethod
    async def upsert_many(
        item_id: str,
        accounts: list[dict[str, Any]],
        *,
        item_label: str | None = None,
        institution_id: str | None = None,
        institution_name: str | None = None,
    ) -> int:
        db = get_database()
        now = _utcnow()
        count = 0
        for account in accounts:
            account_id = account.get("account_id")
            if not account_id:
                continue
            summary = account_summary(account)
            doc = {
                "account_id": account_id,
                "item_id": item_id,
                "item_label": item_label,
                "institution_id": institution_id,
                "institution_name": institution_name,
                **summary,
                "display_name": display_name(summary),
                "data": to_bson_safe(account),
                "updated_at": now,
            }
            await db.accounts.update_one(
                {"account_id": account_id},
                {"$set": doc},
                upsert=True,
            )
            count += 1
        return count

    @staticmethod
    async def get_by_account_id(account_id: str) -> dict[str, Any] | None:
        db = get_database()
        return await db.accounts.find_one({"account_id": account_id})

    @staticmethod
    async def list_for_item(item_id: str) -> list[dict[str, Any]]:
        db = get_database()
        cursor = db.accounts.find({"item_id": item_id}).sort("name", 1)
        return await cursor.to_list(length=None)

    @staticmethod
    def summaries_by_id(accounts: list[dict[str, Any]], *, item_label: str | None = None) -> dict[str, dict[str, Any]]:
        """Map account_id → denormalized fields for transaction writes."""
        result: dict[str, dict[str, Any]] = {}
        for account in accounts:
            account_id = account.get("account_id")
            if not account_id:
                continue
            summary = account_summary(account)
            result[account_id] = {
                "account_name": summary.get("name"),
                "account_official_name": summary.get("official_name"),
                "account_type": summary.get("type"),
                "account_subtype": summary.get("subtype"),
                "account_mask": summary.get("mask"),
                "account_display_name": display_name(summary),
                "item_label": item_label,
            }
        return result


class TransactionRepository:
    @staticmethod
    async def apply_sync(
        item_id: str,
        *,
        added: list[dict[str, Any]],
        modified: list[dict[str, Any]],
        removed: list[dict[str, Any]],
        account_fields: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        db = get_database()
        now = _utcnow()
        stats: dict[str, int] = {
            "upserted": 0,
            "removed": 0,
            "analyzed_transactions": 0,
            "analysis_reviews": 0,
            "analysis_state": 0,
        }

        for tx in added + modified:
            tx_id = tx.get("transaction_id")
            if not tx_id:
                continue
            fields: dict[str, Any] = {
                "transaction_id": tx_id,
                "item_id": item_id,
                "account_id": tx.get("account_id"),
                "data": to_bson_safe(tx),
                "updated_at": now,
            }
            acct_id = tx.get("account_id")
            if account_fields and acct_id and acct_id in account_fields:
                fields.update(account_fields[acct_id])
            await db.transactions.update_one(
                {"transaction_id": tx_id},
                {"$set": fields},
                upsert=True,
            )
            stats["upserted"] += 1

        removed_ids: list[str] = []
        for tx in removed:
            tx_id = tx.get("transaction_id")
            if not tx_id:
                continue
            await db.transactions.delete_one({"transaction_id": tx_id})
            removed_ids.append(tx_id)
            stats["removed"] += 1

        if removed_ids:
            cleanup = await delete_analysis_artifacts_for_transactions(removed_ids)
            stats["analyzed_transactions"] = cleanup["analyzed_transactions"]
            stats["analysis_reviews"] = cleanup["analysis_reviews"]
            stats["analysis_state"] = cleanup["analysis_state"]

        return stats

    @staticmethod
    async def count_for_item(item_id: str) -> int:
        db = get_database()
        return await db.transactions.count_documents({"item_id": item_id})
