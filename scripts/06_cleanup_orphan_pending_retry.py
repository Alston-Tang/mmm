#!/usr/bin/env python3
"""Remove pending_retry queue entries whose source transaction no longer exists."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from pymongo import MongoClient

PENDING_RETRY_STATUS = "pending_retry"


def _log(message: str) -> None:
    print(f"[cleanup] {message}")


def _load_env_file() -> None:
    """Load key=value pairs from repo .env into process env if missing."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _parse_args() -> argparse.Namespace:
    _load_env_file()
    parser = argparse.ArgumentParser(
        description=(
            "Delete orphan pending_retry rows from transaction_analysis_state "
            "when the linked source transaction is missing from transactions."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--mongodb-uri",
        default=os.getenv("MONGODB_URI"),
        help="MongoDB URI. Defaults to env MONGODB_URI.",
    )
    parser.add_argument(
        "--mongodb-database",
        default=os.getenv("MONGODB_DATABASE", "mmm"),
        help="MongoDB database name. Defaults to env MONGODB_DATABASE or 'mmm'.",
    )
    return parser.parse_args()


def _source_filter(transaction_ids: list[str]) -> dict[str, Any]:
    return {
        "$or": [
            {"source_transaction_id": {"$in": transaction_ids}},
            {"source_transaction_ids": {"$in": transaction_ids}},
        ],
    }


def _run(*, apply: bool, mongodb_uri: str, mongodb_database: str) -> None:
    _log(
        f"connecting to database='{mongodb_database}' "
        f"mode={'APPLY' if apply else 'DRY-RUN'}"
    )
    client = MongoClient(mongodb_uri)
    db = client[mongodb_database]
    state_coll = db.transaction_analysis_state
    source_coll = db.transactions

    scanned = 0
    orphan_state_ids: list[Any] = []
    orphan_tx_ids: list[str] = []
    deleted_state = 0
    deleted_analyzed = 0
    deleted_reviews = 0

    try:
        states = list(
            state_coll.find(
                {"status": PENDING_RETRY_STATUS},
                {
                    "_id": 1,
                    "transaction_id": 1,
                    "user_comment": 1,
                    "updated_at": 1,
                },
            )
        )
        _log(f"found {len(states)} pending_retry state document(s)")

        for state in states:
            scanned += 1
            tx_id = state.get("transaction_id")
            if not isinstance(tx_id, str) or not tx_id:
                _log(f"orphan(missing transaction_id) state_id={state.get('_id')}")
                orphan_state_ids.append(state["_id"])
                continue

            exists = source_coll.count_documents({"transaction_id": tx_id}, limit=1)
            if exists:
                continue

            comment = (state.get("user_comment") or "").strip()
            preview = comment[:80] + "..." if len(comment) > 80 else (comment or "(none)")
            _log(
                f"orphan(missing source tx) transaction_id={tx_id} "
                f"updated_at={state.get('updated_at')} comment={preview}"
            )
            orphan_state_ids.append(state["_id"])
            orphan_tx_ids.append(tx_id)

        _log(f"orphan pending_retry total={len(orphan_state_ids)}")

        if apply and orphan_state_ids:
            state_result = state_coll.delete_many({"_id": {"$in": orphan_state_ids}})
            deleted_state = state_result.deleted_count

            if orphan_tx_ids:
                source_filter = _source_filter(orphan_tx_ids)
                analyzed_result = db.analyzed_transactions.delete_many(source_filter)
                deleted_analyzed = analyzed_result.deleted_count

                reviews_result = db.analysis_reviews.delete_many(source_filter)
                deleted_reviews = reviews_result.deleted_count

            _log(
                f"deleted state={deleted_state} analyzed={deleted_analyzed} "
                f"reviews={deleted_reviews}"
            )
    finally:
        client.close()
        _log("database connection closed")

    mode = "APPLY" if apply else "DRY-RUN"
    print(
        f"[{mode}] scanned={scanned} orphan_pending_retry={len(orphan_state_ids)} "
        f"deleted_state={deleted_state} deleted_analyzed={deleted_analyzed} "
        f"deleted_reviews={deleted_reviews}"
    )


def main() -> None:
    args = _parse_args()
    if not args.mongodb_uri:
        raise ValueError("Missing MongoDB URI. Set MONGODB_URI or pass --mongodb-uri.")
    _run(
        apply=args.apply,
        mongodb_uri=args.mongodb_uri,
        mongodb_database=args.mongodb_database,
    )


if __name__ == "__main__":
    main()
