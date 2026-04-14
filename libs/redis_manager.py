import asyncio
from typing import Awaitable, Callable

import redis.asyncio as redis

from libs.logger import logger


class RedisManager:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.pool: redis.ConnectionPool | None = None
        logger.info(f"RedisManager configured for {self.redis_url}")

    async def init_pool(self) -> None:
        self.pool = redis.ConnectionPool.from_url(
            self.redis_url, max_connections=10, decode_responses=True
        )
        logger.info(f"Redis connection pool initialised at {self.redis_url}.")

    async def close_pool(self) -> None:
        """Drain and close the connection pool. Call at app shutdown."""
        if self.pool:
            await self.pool.aclose()
            logger.info("Redis connection pool closed.")

    def get_client(self) -> redis.Redis:
        if self.pool:
            return redis.Redis(connection_pool=self.pool)
        # Lazy fallback — no pool yet (e.g. during startup before lifespan runs)
        return redis.Redis.from_url(self.redis_url, decode_responses=True)

    async def start_subscriber(
        self,
        channel: str,
        callback: Callable[[str, str], Awaitable[None]],
    ) -> None:
        logger.info(f"Starting Redis subscriber for pattern: {channel}")
        client = self.get_client()
        pubsub = client.pubsub()
        await pubsub.psubscribe(channel)
        logger.info(f"Subscribed to pattern '{channel}'. Awaiting messages…")

        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    await callback(message["data"], message["channel"])
        except asyncio.CancelledError:
            logger.info(f"Subscriber for '{channel}' cancelled — shutting down.")
        finally:
            await pubsub.aclose()

from libs.config import get_settings as _get_settings

_settings = _get_settings()

_raw = _settings.redis_host.strip()
if not _raw.startswith("redis://"):
    _redis_url = f"redis://{_raw}/0"
else:
    _redis_url = _raw

redis_manager = RedisManager(redis_url=_redis_url)


async def get_redis():
    client = redis_manager.get_client()
    try:
        yield client
    finally:
        await client.aclose()