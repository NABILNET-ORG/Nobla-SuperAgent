from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from nobla.config.settings import Settings


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            settings.database.postgres_url,
            echo=settings.server.debug,
            pool_size=5,
            max_overflow=10,
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.redis = Redis.from_url(
            settings.database.redis_url, decode_responses=True
        )

    async def get_session(self):
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
        await self.redis.close()
