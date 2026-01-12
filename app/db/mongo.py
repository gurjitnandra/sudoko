"""MongoDB connection utilities using Motor."""
from __future__ import annotations

from typing import AsyncIterator, Callable

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings


class MongoClientManager:
    """Manage a singleton Motor client and provide database instances."""

    _client: AsyncIOMotorClient | None = None

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncIOMotorClient(settings.mongo_uri)
        return cls._client

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        settings = get_settings()
        return cls.get_client()[settings.mongo_db_name]


async def get_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    """FastAPI dependency that yields the default database."""

    db = MongoClientManager.get_database()
    yield db


async def run_transaction(db_callable: Callable[[AsyncIOMotorClient], AsyncIterator[None]]) -> None:
    """Helper to run a MongoDB transaction given a coroutine factory."""

    client = MongoClientManager.get_client()
    async with await client.start_session() as session:
        async with session.start_transaction():
            async for _ in db_callable(session):
                pass
