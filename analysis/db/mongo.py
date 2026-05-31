from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from analysis.config import get_settings

# Collections owned and written by the sync service — analysis must never modify these.
SYNC_OWNED_COLLECTIONS = frozenset({"items", "accounts", "transactions"})

# Collections owned and written by the analysis service.
ANALYSIS_OWNED_COLLECTIONS = frozenset({
    "analyzed_transactions",
    "transaction_analysis_state",
    "analysis_reviews",
})

# Allowed read-only methods on sync-owned collections.
_READ_ONLY_METHODS = frozenset(
    {
        "find",
        "find_one",
        "count_documents",
        "aggregate",
        "distinct",
        "estimated_document_count",
    }
)

_client: AsyncIOMotorClient | None = None


class ReadOnlyCollection:
    """Wraps a Motor collection and blocks all write / schema operations."""

    def __init__(self, collection: Any, *, owner: str) -> None:
        self._collection = collection
        self._owner = owner

    @property
    def name(self) -> str:
        return self._collection.name

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in _READ_ONLY_METHODS:
            raise PermissionError(
                f"Analysis service cannot modify sync-owned collection '{self._collection.name}' "
                f"(owned by {self._owner}): '{name}' is not allowed (read-only)."
            )
        return getattr(self._collection, name)


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def _raw_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.mongodb_database]


def get_sync_collection(name: str) -> ReadOnlyCollection:
    """Read-only access to a collection owned by the sync service."""
    if name not in SYNC_OWNED_COLLECTIONS:
        raise ValueError(
            f"Unknown sync collection '{name}'. "
            f"Allowed: {sorted(SYNC_OWNED_COLLECTIONS)}"
        )
    return ReadOnlyCollection(_raw_database()[name], owner="sync service")


def get_analysis_collection(name: str):
    """Read/write access to a collection owned by the analysis service."""
    if name not in ANALYSIS_OWNED_COLLECTIONS:
        raise ValueError(
            f"Collection '{name}' is not owned by the analysis service. "
            f"Use get_sync_collection() for read-only access to sync data. "
            f"Analysis-owned: {sorted(ANALYSIS_OWNED_COLLECTIONS)}"
        )
    return _raw_database()[name]


async def ping_database() -> None:
    await _raw_database().command("ping")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    """Create indexes only on analysis-owned collections."""
    analyzed = get_analysis_collection("analyzed_transactions")
    state = get_analysis_collection("transaction_analysis_state")

    await analyzed.create_index("analyzed_transaction_id", unique=True)
    await analyzed.create_index("source_transaction_id")
    await analyzed.create_index("analysis_id")
    await analyzed.create_index("category")
    await analyzed.create_index("is_subscription")
    await analyzed.create_index("transaction_date")

    await state.create_index("transaction_id", unique=True)
    await state.create_index("status")
    await state.create_index("analysis_id")

    reviews = get_analysis_collection("analysis_reviews")
    await reviews.create_index("review_id", unique=True)
    await reviews.create_index("analysis_id")
    await reviews.create_index("source_transaction_id")
    await reviews.create_index("attention_type")
    await reviews.create_index("created_at")
