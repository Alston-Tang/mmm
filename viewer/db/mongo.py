from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from viewer.config import get_settings

READABLE_COLLECTIONS = frozenset({
    "analyzed_transactions",
    "transaction_analysis_state",
    "analysis_reviews",
    "transactions",
})

WRITABLE_COLLECTIONS = frozenset({
    "analyzed_transactions",
    "transaction_analysis_state",
    "analysis_reviews",
})

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
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in _READ_ONLY_METHODS:
            raise PermissionError(
                f"Viewer cannot modify collection '{self._collection.name}': "
                f"'{name}' is not allowed (read-only)."
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


def get_collection(name: str) -> ReadOnlyCollection:
    if name not in READABLE_COLLECTIONS:
        raise ValueError(f"Collection '{name}' is not readable by the viewer service")
    return ReadOnlyCollection(_raw_database()[name])


def get_writable_collection(name: str):
    if name not in WRITABLE_COLLECTIONS:
        raise ValueError(f"Collection '{name}' is not writable by the viewer service")
    return _raw_database()[name]


async def ping_database() -> None:
    await _raw_database().command("ping")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
