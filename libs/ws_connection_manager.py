import asyncio
from fastapi import WebSocket
from redis.asyncio import Redis

from libs.logger import logger
from libs.redis_manager import get_redis, redis_manager


class ConnectionManager:
    def __init__(
        self,
    ):
        self.active_connections: dict[str, WebSocket] = {}
        self.redis = redis_manager.get_client()

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        # await self.redis.clset(redis_key, "online", ex=60)
        redis_key = f"status:{session_id}"
        await self.redis.set(redis_key, "online", ex=60 * 100)
        logger.info(f"New connection established for session_id: {session_id}")

    async def disconnect(self, session_id: str):
        logger.info(f"clinet disconnected {session_id}")
        self.active_connections.pop(session_id, None)
        redis_key = f"status:{session_id}"
        await self.redis.delete(redis_key, "online")

    async def send_personal_message(self, message: dict[str, str], session_id: str):
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await asyncio.wait_for(websocket.send_json(message), timeout=5.0)
                logger.info(f"Sent message to {session_id}: {message}")
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                await self.disconnect(session_id)
        else:
            logger.warning(
                f"Attempted to send message to {session_id} but no active connection found."
            )


ws_manager = ConnectionManager()
