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


redis_manager = RedisManager(host="localhost", port=6379)
