from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from sync.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.mongodb_database]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ensure_indexes() -> None:
    db = get_database()
    await db.items.create_index("item_id", unique=True)
    await db.transactions.create_index("transaction_id", unique=True)
    await db.transactions.create_index("item_id")
    await db.transactions.create_index("account_id")
    await db.accounts.create_index("account_id", unique=True)
    await db.accounts.create_index("item_id")
