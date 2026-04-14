import asyncio
from fastapi import WebSocket

from libs.logger import logger
from libs.redis_manager import redis_manager

_SESSION_TTL_SECONDS = 60 * 100


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.redis = redis_manager.get_client()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[session_id] = websocket

        redis_key = f"status:{session_id}"
        await self.redis.set(redis_key, "online", ex=_SESSION_TTL_SECONDS)

        logger.info(f"WebSocket connected — session_id={session_id}")

    async def disconnect(self, session_id: str) -> None:
        self.active_connections.pop(session_id, None)
        redis_key = f"status:{session_id}"
        await self.redis.delete(redis_key)
        logger.info(f"WebSocket disconnected — session_id={session_id}")

    async def send_personal_message(
        self, message: dict, session_id: str
    ) -> None:
        websocket = self.active_connections.get(session_id)
        if websocket is None:
            logger.warning(
                f"No active WebSocket for session_id={session_id} — message dropped."
            )
            return

        try:
            await asyncio.wait_for(websocket.send_json(message), timeout=5.0)
            logger.info(f"Message delivered to session_id={session_id}: {message}")
        except Exception as e:
            logger.error(
                f"Failed to deliver message to session_id={session_id}: {e}"
            )
            await self.disconnect(session_id)


ws_manager = ConnectionManager()