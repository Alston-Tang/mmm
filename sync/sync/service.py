from __future__ import annotations

import asyncio
import logging
from typing import Any

from sync.db.repository import AccountRepository, ItemRepository, TransactionRepository
from sync.plaid.accounts import fetch_accounts
from sync.plaid.sync import fetch_sync_pages

logger = logging.getLogger(__name__)


def _merge_accounts_by_id(*groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for account in group:
            account_id = account.get("account_id")
            if account_id:
                merged[account_id] = account
    return merged


async def _sync_accounts_metadata(
    item: dict[str, Any],
    sync_page_accounts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Persist accounts to MongoDB; return map for transaction denormalization."""
    item_id = item["item_id"]
    access_token = item["access_token"]
    item_label = item.get("label")

    accounts_get = await asyncio.to_thread(fetch_accounts, access_token)
    api_accounts = accounts_get.get("accounts", [])
    plaid_item = accounts_get.get("item") or {}

    institution_id = plaid_item.get("institution_id") or item.get("institution_id")
    institution_name = item.get("institution_name")

    merged = _merge_accounts_by_id(sync_page_accounts, api_accounts)
    account_list = list(merged.values())

    await AccountRepository.upsert_many(
        item_id,
        account_list,
        item_label=item_label,
        institution_id=institution_id,
        institution_name=institution_name,
    )

    if institution_id:
        await ItemRepository.update_institution(
            item_id,
            institution_id=institution_id,
            institution_name=institution_name,
        )

    return AccountRepository.summaries_by_id(account_list, item_label=item_label)


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

        sync_accounts: list[dict[str, Any]] = []
        for page in pages:
            sync_accounts.extend(page.accounts)

        account_fields = await _sync_accounts_metadata(item, sync_accounts)

        total_added = 0
        total_modified = 0
        total_removed = 0
        analysis_cleanup = {
            "analyzed_transactions": 0,
            "analysis_reviews": 0,
            "analysis_state": 0,
            "pending_retry_state": 0,
        }

        for page in pages:
            stats = await TransactionRepository.apply_sync(
                item_id,
                added=page.added,
                modified=page.modified,
                removed=page.removed,
                account_fields=account_fields,
            )
            total_added += len(page.added)
            total_modified += len(page.modified)
            total_removed += stats["removed"]
            for key in analysis_cleanup:
                analysis_cleanup[key] += stats.get(key, 0)

        final_cursor = pages[-1].next_cursor if pages else cursor
        if final_cursor:
            await ItemRepository.update_cursor(item_id, final_cursor)

        await ItemRepository.mark_sync_result(item_id)
        tx_count = await TransactionRepository.count_for_item(item_id)
        account_count = len(await AccountRepository.list_for_item(item_id))

        return {
            "item_id": item_id,
            "label": item.get("label"),
            "added": total_added,
            "modified": total_modified,
            "removed": total_removed,
            "analysis_cleanup": analysis_cleanup,
            "stored_transactions": tx_count,
            "stored_accounts": account_count,
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
