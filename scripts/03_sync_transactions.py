#!/usr/bin/env python3
"""Step 3: Sync transactions for all linked Items (all accounts per Item)."""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cursor_store import list_access_tokens
from transactions_sync import sync_all_items


def main() -> None:
    tokens = list_access_tokens()
    if not tokens:
        print("No access tokens. Run 00_sandbox_quick_link.py or 02_exchange_public_token.py first.")
        sys.exit(1)

    reset = "--reset" in sys.argv
    account_id = os.getenv("PLAID_ACCOUNT_ID")

    results = sync_all_items(tokens, account_id=account_id or None, reset_cursor=reset)

    for r in results:
        by_account: dict[str, list] = defaultdict(list)
        for tx in r.added:
            by_account[tx.get("account_id", "unknown")].append(tx)

        print(f"\n=== Item (token …{r.access_token[-8:]}) ===")
        print(f"Accounts seen: {len(r.accounts) or len(by_account)}")
        print(f"Added: {len(r.added)}, Modified: {len(r.modified)}, Removed: {len(r.removed)}")
        print(f"Cursor saved: {r.next_cursor[:20]}..." if r.next_cursor else "No cursor")

        for acct_id, txs in sorted(by_account.items()):
            name = next(
                (a.get("name") for a in r.accounts if a.get("account_id") == acct_id),
                acct_id,
            )
            print(f"\n  {name} ({acct_id}): {len(txs)} transactions")
            for tx in txs[:3]:
                amount = tx.get("amount")
                date = tx.get("date")
                merchant = tx.get("merchant_name") or tx.get("name")
                print(f"    {date}  ${amount:>8}  {merchant}")
            if len(txs) > 3:
                print(f"    ... and {len(txs) - 3} more")

    # Full JSON to stdout if requested
    if "--json" in sys.argv:
        payload = [
            {
                "access_token_suffix": r.access_token[-8:],
                "added": r.added,
                "modified": r.modified,
                "removed": r.removed,
                "accounts": r.accounts,
            }
            for r in results
        ]
        print("\n" + json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
