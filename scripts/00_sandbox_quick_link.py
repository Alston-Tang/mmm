#!/usr/bin/env python3
"""
Sandbox shortcut: create a test Item without Plaid Link UI.

Uses /sandbox/public_token/create then exchanges for access_token.
Institution: First Platypus Bank (ins_109508) — typical sandbox multi-account bank.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest

from cursor_store import save_access_token
from plaid_client import get_plaid_client


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "sandbox-first-platypus"
    institution_id = sys.argv[2] if len(sys.argv) > 2 else "ins_109508"

    client = get_plaid_client()

    sandbox_response = client.sandbox_public_token_create(
        SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products("transactions")],
        )
    )
    public_token = sandbox_response.to_dict()["public_token"]

    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

    exchange = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    body = exchange.to_dict()
    save_access_token(label, body["access_token"])

    print(json.dumps(body, indent=2))
    print("\nSandbox Item ready. Wait ~10s, then run scripts/03_sync_transactions.py")


if __name__ == "__main__":
    main()
