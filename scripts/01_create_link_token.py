#!/usr/bin/env python3
"""Step 1: Create a Link token to open Plaid Link in your frontend."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from plaid_client import get_plaid_client, require_env


def main() -> None:
    client = get_plaid_client()
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user-1"
    days_requested = int(os.getenv("PLAID_DAYS_REQUESTED", "90"))

    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="MMM Transactions",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        # Optional: webhook for SYNC_UPDATES_AVAILABLE
        # webhook="https://your-server.com/plaid/webhook",
        transactions={"days_requested": days_requested},
    )

    response = client.link_token_create(request)
    print(json.dumps(response.to_dict(), indent=2))
    print("\nUse link_token with Plaid Link. After success, run 02_exchange_public_token.py <public_token>")


if __name__ == "__main__":
    main()
