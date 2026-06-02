#!/usr/bin/env python3
"""Remove analyzed transactions whose source transaction no longer exists."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from pymongo import MongoClient


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
            "Delete orphan rows from analyzed_transactions where linked source "
            "transaction IDs are no longer present in transactions."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of analyzed rows to scan per batch (default: 500).",
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


def _source_ids(doc: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    primary = doc.get("source_transaction_id")
    if isinstance(primary, str) and primary:
        source_ids.append(primary)
    extra = doc.get("source_transaction_ids")
    if isinstance(extra, list):
        source_ids.extend(x for x in extra if isinstance(x, str) and x)
    return list(dict.fromkeys(source_ids))


def _run(*, apply: bool, batch_size: int, mongodb_uri: str, mongodb_database: str) -> None:
    _log(
        f"connecting to database='{mongodb_database}' "
        f"mode={'APPLY' if apply else 'DRY-RUN'} batch_size={batch_size}"
    )
    client = MongoClient(mongodb_uri)
    db = client[mongodb_database]
    analyzed_coll = db.analyzed_transactions
    source = db.transactions

    scanned = 0
    orphaned = 0
    delete_count = 0
    last_id: Any = None
    batch_no = 0

    try:
        while True:
            batch_no += 1
            query: dict[str, Any] = {}
            if last_id is not None:
                query["_id"] = {"$gt": last_id}

            batch = list(
                analyzed_coll.find(
                    query,
                    {
                        "_id": 1,
                        "analyzed_transaction_id": 1,
                        "source_transaction_id": 1,
                        "source_transaction_ids": 1,
                    },
                ).sort("_id", 1).limit(batch_size)
            )
            if not batch:
                break
            _log(f"batch {batch_no}: loaded {len(batch)} analyzed transaction(s)")

            orphan_ids: list[Any] = []
            for doc in batch:
                scanned += 1
                ids = _source_ids(doc)
                if not ids:
                    atx_id = doc.get("analyzed_transaction_id", str(doc.get("_id")))
                    _log(f"batch {batch_no}: orphan(no source ids) analyzed_transaction_id={atx_id}")
                    orphan_ids.append(doc["_id"])
                    continue

                existing = source.count_documents({"transaction_id": {"$in": ids}}, limit=1)
                if existing == 0:
                    atx_id = doc.get("analyzed_transaction_id", str(doc.get("_id")))
                    _log(
                        f"batch {batch_no}: orphan(missing source tx) "
                        f"analyzed_transaction_id={atx_id} source_ids={ids}"
                    )
                    orphan_ids.append(doc["_id"])

            orphaned += len(orphan_ids)
            _log(
                f"batch {batch_no}: scanned_total={scanned} "
                f"orphan_in_batch={len(orphan_ids)} orphan_total={orphaned}"
            )

            if apply and orphan_ids:
                result = analyzed_coll.delete_many({"_id": {"$in": orphan_ids}})
                delete_count += result.deleted_count
                _log(
                    f"batch {batch_no}: deleted_in_batch={result.deleted_count} "
                    f"deleted_total={delete_count}"
                )

            last_id = batch[-1]["_id"]
    finally:
        client.close()
        _log("database connection closed")

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] scanned={scanned} orphaned={orphaned} deleted={delete_count}")


def main() -> None:
    args = _parse_args()
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if not args.mongodb_uri:
        raise ValueError("Missing MongoDB URI. Set MONGODB_URI or pass --mongodb-uri.")
    _run(
        apply=args.apply,
        batch_size=args.batch_size,
        mongodb_uri=args.mongodb_uri,
        mongodb_database=args.mongodb_database,
    )


if __name__ == "__main__":
    main()
