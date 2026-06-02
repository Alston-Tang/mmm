from __future__ import annotations

import logging
from typing import Any

from sync.db.mongo import get_database

logger = logging.getLogger(__name__)


def _source_transaction_filter(transaction_ids: list[str]) -> dict[str, Any]:
    return {
        "$or": [
            {"source_transaction_id": {"$in": transaction_ids}},
            {"source_transaction_ids": {"$in": transaction_ids}},
        ],
    }


async def delete_analysis_artifacts_for_transactions(
    transaction_ids: list[str],
) -> dict[str, int]:
    """Remove analysis data for Plaid transactions that no longer exist in sync.

    When a pending charge posts, Plaid removes the pending transaction_id and adds
    a new one. Any analyzed rows tied to the removed id would otherwise be orphaned.
    """
    if not transaction_ids:
        return {
            "analyzed_transactions": 0,
            "analysis_reviews": 0,
            "analysis_state": 0,
        }

    db = get_database()
    source_filter = _source_transaction_filter(transaction_ids)

    analyzed_result = await db.analyzed_transactions.delete_many(source_filter)
    reviews_result = await db.analysis_reviews.delete_many(source_filter)
    state_result = await db.transaction_analysis_state.delete_many(
        {"transaction_id": {"$in": transaction_ids}},
    )

    stats = {
        "analyzed_transactions": analyzed_result.deleted_count,
        "analysis_reviews": reviews_result.deleted_count,
        "analysis_state": state_result.deleted_count,
    }
    if any(stats.values()):
        logger.info(
            "Removed analysis artifacts for %d deleted transaction(s): %s",
            len(transaction_ids),
            stats,
        )
    return stats
