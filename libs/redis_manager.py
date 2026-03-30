import asyncio
from typing import Awaitable, Callable
import redis.asyncio as redis

from libs.logger import logger


class RedisManager:
    def __init__(self, host: str, port: int, db: int = 0):
        self.redis_url = f"redis://{host}:{port}/{db}"
        self.pool = None

    async def init_pool(self):
        """Initialize the connection pool."""
        # max_connections helps manage resource limits
        self.pool = redis.ConnectionPool.from_url(
            self.redis_url, max_connections=10, decode_responses=True
        )
        logger.info(f"Redis connection pool initialized at {self.redis_url}.")

    async def close_pool(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.disconnect()
            logger.info("Redis connection pool closed.")

    def get_client(self) -> redis.Redis:
        """Returns a Redis client from the pool."""
        return redis.Redis(connection_pool=self.pool)

    async def start_subscriber(
        self, channel: str, callback: Callable[[str, str], Awaitable[None]]
    ):
        """
        Listens for messages and executes the provided async callback.
        """
        logger.info(f"Starting subscriber for channel: {channel}")
        client = self.get_client()
        pubsub = client.pubsub()
        await pubsub.psubscribe(channel)
        logger.info(f"Subscribed to {channel}. Awaiting messages...")

        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    data = message["data"]
                    channel = message["channel"]
                    await callback(data, channel)
        except asyncio.CancelledError:
            logger.info(f"Closing subscriber for {channel}")
        finally:
            await pubsub.close()


redis_manager = RedisManager(host="localhost", port=6379)


async def get_redis():
    client = redis_manager.get_client()
    try:
        yield client
    finally:
        await client.close()
