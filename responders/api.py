# WebSocket endpoint (/v1/ws/receive/{session_id}) — Redis pub/sub subscriber for response delivery
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from libs.logger import logger
from libs.redis_manager import get_redis, redis_manager
from libs.validation import SESSION_ID_RE
from libs.ws_connection_manager import ws_manager

router = APIRouter()


# WebSocket handler: validates session_id, starts the Redis psubscribe loop, and streams responses to the client
@router.websocket("/receive/{session_id}")
async def chat_socket(
    websocket: WebSocket,
    session_id: str,
    redis: Redis = Depends(get_redis),
) -> None:
    if not SESSION_ID_RE.match(session_id):
        logger.warning(f"Rejected WebSocket — invalid session_id format: {session_id!r}")
        await websocket.close(code=1008)
        return
    await ws_manager.connect(session_id, websocket)

    # Callback passed to start_subscriber; forwards each Redis message directly to the open WebSocket
    async def send_to_client(data: str, channel: str) -> None:
        try:
            await websocket.send_text(data)
            logger.info(f"Forwarded Redis message to session_id={session_id}")
        except WebSocketDisconnect:
            logger.info(f"Client disconnected mid-send — session_id={session_id}")
            raise
        except Exception as e:
            logger.error(f"Error forwarding message to session_id={session_id}: {e}")
            raise

    try:
        channel_pattern = f"user_{session_id}"
        await redis_manager.start_subscriber(channel_pattern, send_to_client)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected — session_id={session_id}")

    except Exception as e:
        logger.error(f"Unexpected error in WebSocket handler for session_id={session_id}: {e}")

    finally:
        await ws_manager.disconnect(session_id)
        logger.info(f"Cleaned up session_id={session_id}")
