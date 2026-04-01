import asyncio
import json
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import EventSourceResponse
from redis.asyncio import Redis

from libs.logger import logger
from libs.redis_manager import RedisManager, get_redis, redis_manager
from libs.ws_connection_manager import ws_manager

router = APIRouter()


@router.websocket("/receive/{session_id}")
async def chat_socket(
    websocket: WebSocket,
    session_id: str,
    redis: Redis = Depends(get_redis),  # Assuming you provide the manager
):
    await ws_manager.connect(session_id, websocket)

    # Define what happens when a message is received from Redis
    async def send_to_client(data: str, channel: str):
        try:
            await websocket.send_text(data)
            logger.info(f"Sent message to client {session_id}: {data}")
        except Exception as e:
            logger.error(f"Error sending message to client {session_id}: {e}")

    redis_key = f"status:{session_id}"
    await redis.set(redis_key, "online", ex=60)

    try:
        channel_pattern = f"user_{session_id}"
        await redis_manager.start_subscriber(channel_pattern, send_to_client)

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)
    finally:
        # Cleanup status
        await redis.delete(redis_key)


@router.get("/stream/{session_id}")
async def chat_stream(
    request: Request, session_id: str, redis: Redis = Depends(get_redis)
):
    redis_key = f"status:{session_id}"
    channel_name = f"user_{session_id}"

    await redis.set(redis_key, "online", ex=60)

    # if await request.is_disconnected():
    #     await redis.delete(redis_key)
    #     return

    async def event_generator():
        pubsub = redis.pubsub()
        try:
            await pubsub.psubscribe(channel_name)

            while True:
                # 2. DISCONNECT CHECK
                if await request.is_disconnected():
                    await redis.delete(redis_key)
                    break

                # listen() is an async generatoe
                async for message in pubsub.listen():
                    # Refresh TTL to keep them online while active
                    await redis.expire(redis_key, 60)

                    if message["type"] == "pmessage":
                        data = message["data"].decode("utf-8")
                        logger.info(f"Sending message for session {session_id}: {data}")
                        yield f"{json.dumps({'msg': data})}\n\n"
                        yield f"{json.dumps({'msg': '[DONE]'})}\n\n"

                    # Check disconnect again inside the inner loop
                    if await request.is_disconnected():
                        await redis.delete(redis_key)
                        return

        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            await pubsub.close()
            await redis.delete(redis_key)
            logger.info(f"Cleaned up session: {session_id}")

    return EventSourceResponse(event_generator())
