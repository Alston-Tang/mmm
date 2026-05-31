from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plaid.model.transactions_sync_request import TransactionsSyncRequest

from sync.plaid.client import get_plaid_client


@dataclass
class SyncPage:
    added: list[dict[str, Any]] = field(default_factory=list)
    modified: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: str | None = None


def _to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


def fetch_sync_pages(
    access_token: str,
    *,
    cursor: str | None = None,
    account_id: str | None = None,
) -> list[SyncPage]:
    """Fetch all pages from /transactions/sync for one Item."""
    client = get_plaid_client()
    pages: list[SyncPage] = []

    while True:
        request_kwargs: dict[str, Any] = {
            "access_token": access_token,
            "count": 500,
        }
        if cursor is not None:
            request_kwargs["cursor"] = cursor
        if account_id:
            request_kwargs["account_id"] = account_id

        response = client.transactions_sync(TransactionsSyncRequest(**request_kwargs))
        body = response.to_dict()

        page = SyncPage(
            added=[_to_dict(t) for t in body.get("added", [])],
            modified=[_to_dict(t) for t in body.get("modified", [])],
            removed=[_to_dict(t) for t in body.get("removed", [])],
            accounts=[_to_dict(a) for a in body.get("accounts", [])],
            next_cursor=body.get("next_cursor"),
        )
        pages.append(page)

        cursor = page.next_cursor
        if not body.get("has_more"):
            break

    return pages
