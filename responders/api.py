from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from libs.logger import logger
from libs.redis_manager import get_redis, redis_manager
from libs.ws_connection_manager import ws_manager

router = APIRouter()


@router.websocket("/receive/{session_id}")
async def chat_socket(
    websocket: WebSocket,
    session_id: str,
    redis: Redis = Depends(get_redis),
) -> None:
    await ws_manager.connect(session_id, websocket)

    async def send_to_client(data: str, channel: str) -> None:
        try:
            await websocket.send_text(data)
            logger.info(f"Forwarded Redis message to session_id={session_id}")
        except WebSocketDisconnect:
            logger.info(
                f"Client disconnected mid-send — session_id={session_id}"
            )
            raise  # re-raise so start_subscriber's CancelledError path cleans up
        except Exception as e:
            logger.error(
                f"Error forwarding message to session_id={session_id}: {e}"
            )

    try:
        channel_pattern = f"user_{session_id}"
        await redis_manager.start_subscriber(channel_pattern, send_to_client)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected — session_id={session_id}")

    except Exception as e:
        logger.error(
            f"Unexpected error in WebSocket handler for session_id={session_id}: {e}"
        )

    finally:
        await ws_manager.disconnect(session_id)
        logger.info(f"Cleaned up session_id={session_id}")