#!/usr/bin/env python3
"""Step 2: Exchange the public_token from Link for a long-lived access_token."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

from cursor_store import save_access_token
from plaid_client import get_plaid_client


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/02_exchange_public_token.py <public_token> [label]")
        sys.exit(1)

    public_token = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else "default"

    client = get_plaid_client()
    response = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    body = response.to_dict()
    access_token = body["access_token"]
    item_id = body["item_id"]

    save_access_token(label, access_token)

    print(json.dumps({"item_id": item_id, "access_token": access_token}, indent=2))
    print("\nSaved to .plaid_access_tokens.json. Or set PLAID_ACCESS_TOKENS in .env")


if __name__ == "__main__":
    main()
