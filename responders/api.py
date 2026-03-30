from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from libs.redis_manager import get_redis
from libs.ws_connection_manager import ws_manager

router = APIRouter()


@router.websocket("/receive/{session_id}")
async def chat_socket(
    websocket: WebSocket, session_id: str, redis: Redis = Depends(get_redis)
):
    await ws_manager.connect(session_id, websocket)
    redis_key = f"status:{session_id}"
    await redis.set(redis_key, "online", ex=3600)

    try:
        while True:
            # Keep the connection open and wait for messages/disconnects
            await websocket.receive_text()

            # Optional: Refresh the expiration on every heartbeat
            await redis.expire(redis_key, 3600)

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)
        # 4. Remove the flag or set it to offline when they leave
        await redis.delete(redis_key)

    except Exception as e:
        ws_manager.disconnect(session_id)
        await redis.delete(redis_key)
