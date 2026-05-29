from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.repository import ItemRepository, TransactionRepository
from app.plaid.sync import fetch_sync_pages

logger = logging.getLogger(__name__)


async def sync_item(item: dict[str, Any], *, reset_cursor: bool = False) -> dict[str, Any]:
    """Sync one Plaid Item and persist results to MongoDB."""
    item_id = item["item_id"]
    access_token = item["access_token"]
    cursor = None if reset_cursor else item.get("cursor")

    try:
        pages = await asyncio.to_thread(
            fetch_sync_pages,
            access_token,
            cursor=cursor,
        )

        total_added = 0
        total_modified = 0
        total_removed = 0
        institution_name = item.get("institution_name")

        for page in pages:
            stats = await TransactionRepository.apply_sync(
                item_id,
                added=page.added,
                modified=page.modified,
                removed=page.removed,
            )
            total_added += len(page.added)
            total_modified += len(page.modified)
            total_removed += stats["removed"]
            if page.accounts and not institution_name:
                institution_name = page.accounts[0].get("name")

        final_cursor = pages[-1].next_cursor if pages else cursor
        if final_cursor:
            await ItemRepository.update_cursor(item_id, final_cursor)

        await ItemRepository.mark_sync_result(item_id, institution_name=institution_name)
        tx_count = await TransactionRepository.count_for_item(item_id)

        return {
            "item_id": item_id,
            "label": item.get("label"),
            "added": total_added,
            "modified": total_modified,
            "removed": total_removed,
            "stored_transactions": tx_count,
            "cursor_updated": bool(final_cursor),
        }
    except Exception as exc:
        logger.exception("Sync failed for item %s", item_id)
        await ItemRepository.mark_sync_result(item_id, error=str(exc))
        raise


async def sync_all_items(*, reset_cursor: bool = False) -> list[dict[str, Any]]:
    items = await ItemRepository.list_active()
    results: list[dict[str, Any]] = []
    for item in items:
        try:
            results.append(await sync_item(item, reset_cursor=reset_cursor))
        except Exception as exc:
            results.append(
                {
                    "item_id": item["item_id"],
                    "label": item.get("label"),
                    "error": str(exc),
                }
            )
    return results
