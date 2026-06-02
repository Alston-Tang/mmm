from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sync.db.mongo import get_database
from sync.wechat.parser import ParsedWeChatTransaction


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WeChatTransactionRepository:
    @staticmethod
    async def insert_import_batch(
        *,
        import_id: str,
        source_filename: str,
        transactions: list[ParsedWeChatTransaction],
    ) -> dict[str, int]:
        db = get_database()
        coll = db.wechat_transactions
        now = _utcnow()
        inserted = 0
        skipped = 0

        for tx in transactions:
            doc: dict[str, Any] = {
                "wechat_transaction_id": str(uuid.uuid4()),
                "import_id": import_id,
                "transaction_time": tx.transaction_time,
                "transaction_date": tx.transaction_date,
                "transaction_type": tx.transaction_type,
                "counterparty": tx.counterparty,
                "product": tx.product,
                "direction": tx.direction,
                "amount": tx.amount,
                "currency": tx.currency,
                "payment_method": tx.payment_method,
                "status": tx.status,
                "wechat_order_id": tx.wechat_order_id,
                "merchant_order_id": tx.merchant_order_id,
                "remark": tx.remark,
                "source_filename": source_filename,
                "imported_at": now,
            }
            result = await coll.update_one(
                {"wechat_order_id": tx.wechat_order_id},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id is not None:
                inserted += 1
            else:
                skipped += 1

        return {"inserted": inserted, "skipped_duplicates": skipped, "total_in_file": len(transactions)}

    @staticmethod
    async def count() -> int:
        return await get_database().wechat_transactions.count_documents({})

    @staticmethod
    async def list_recent(limit: int = 20) -> list[dict[str, Any]]:
        cursor = (
            get_database()
            .wechat_transactions.find({}, {"_id": 0})
            .sort("transaction_time", -1)
            .limit(limit)
        )
        return [doc async for doc in cursor]
