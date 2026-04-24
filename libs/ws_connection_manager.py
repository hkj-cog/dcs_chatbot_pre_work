# WebSocket connection manager with Redis-backed cross-instance presence tracking
import asyncio
from fastapi import WebSocket

from libs.config import get_settings
from libs.logger import logger
from libs.redis_manager import redis_manager


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    # Accepts a WebSocket connection and registers it with Redis presence tracking
    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        ttl = get_settings().ws_session_ttl_seconds
        redis = redis_manager.get_client()
        try:
            await redis.set(f"status:{session_id}", "online", ex=ttl)
        except Exception as e:
            logger.error(
                f"Redis unavailable — rejecting WebSocket for session_id={session_id}: {e}"
            )
            await websocket.close(code=1011)
            return
        finally:
            await redis.aclose()

        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected — session_id={session_id}")

    # Removes the WebSocket from the local map and clears the Redis presence key
    async def disconnect(self, session_id: str) -> None:
        self.active_connections.pop(session_id, None)

        redis = redis_manager.get_client()
        try:
            await redis.delete(f"status:{session_id}")
        finally:
            await redis.aclose()

        logger.info(f"WebSocket disconnected — session_id={session_id}")

    # Sends a JSON message to the WebSocket for the given session; disconnects on error
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
            logger.info(
                f"Message delivered to session_id={session_id} "
                f"content_length={len(str(message.get('content', '')))} "
                f"refs={len(message.get('references', []))}"
            )
        except Exception as e:
            logger.error(
                f"Failed to deliver message to session_id={session_id}: {e}"
            )
            await self.disconnect(session_id)


ws_manager = ConnectionManager()
