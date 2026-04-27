# WebSocket endpoint (/v1/ws/receive/{session_id}) — Redis pub/sub subscriber for response delivery
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from opentelemetry import trace
from redis.asyncio import Redis

from libs.logger import logger
from libs.observability import record_exception_on_span, with_session_attrs
from libs.redis_manager import get_redis, redis_manager
from libs.validation import SESSION_ID_RE
from libs.ws_connection_manager import ws_manager

router = APIRouter()
_tracer = trace.get_tracer("dcs_chatbot.ws")


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

    async def send_to_client(data: str, channel: str) -> None:
        try:
            await websocket.send_text(data)
            logger.info(
                "Forwarded Redis message to client",
                extra={"session_id": session_id, "channel": channel, "bytes": len(data)},
            )
        except WebSocketDisconnect:
            logger.info(f"Client disconnected mid-send — session_id={session_id}")
            raise
        except Exception as e:
            record_exception_on_span(e)
            logger.error(f"Error forwarding message to session_id={session_id}: {e}")
            raise

    with _tracer.start_as_current_span("ws.receive") as span:
        span.set_attribute("session.id", session_id)
        with with_session_attrs(session_id=session_id, user_id=None):
            try:
                channel_pattern = f"user_{session_id}"
                await redis_manager.start_subscriber(channel_pattern, send_to_client)
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected — session_id={session_id}")
            except Exception as e:
                record_exception_on_span(e)
                logger.error(f"Unexpected error in WebSocket handler for session_id={session_id}: {e}")
            finally:
                await ws_manager.disconnect(session_id)
                logger.info(f"Cleaned up session_id={session_id}")