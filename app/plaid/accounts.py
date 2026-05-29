from __future__ import annotations

from typing import Any

from plaid.model.accounts_get_request import AccountsGetRequest

from app.plaid.client import get_plaid_client
from app.plaid.sync import _to_dict


def fetch_accounts(access_token: str) -> dict[str, Any]:
    """Full account metadata from /accounts/get."""
    client = get_plaid_client()
    response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    body = response.to_dict()
    return {
        "accounts": [_to_dict(a) for a in body.get("accounts", [])],
        "item": _to_dict(body["item"]) if body.get("item") else None,
    }
