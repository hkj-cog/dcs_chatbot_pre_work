# Pub/Sub push webhook (/v1/webhook/chat) — routes completed responses to WebSocket via Redis
import base64
import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from redis.asyncio import Redis

from libs.logger import logger
from libs.redis_manager import get_redis
from libs.validation import SESSION_ID_RE
from receiver.models import PubSubEnvelope

router = APIRouter()


# Pub/Sub push handler: decodes the message, checks WebSocket presence, and publishes to the Redis channel
@router.post("/chat")
async def pubsub_router(envelope: PubSubEnvelope, redis: Redis = Depends(get_redis)):
    try:
        decoded_str = base64.b64decode(envelope.message.data).decode("utf-8")
        payload = json.loads(decoded_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed message body: {e}")

    session_id = envelope.message.attributes.get("session_id")
    if not session_id:
        logger.error("Pub/Sub message missing required session_id attribute")
        raise HTTPException(status_code=400, detail="Missing session_id attribute")
    if not SESSION_ID_RE.match(session_id):
        logger.error(f"Pub/Sub message has invalid session_id format: {session_id!r}")
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    logger.info(
        f"Received Pub/Sub message: session_id={session_id} "
        f"content_length={len(str(payload.get('content', '')))} "
        f"score={payload.get('score')} refs={len(payload.get('references', []))}"
    )

    try:
        is_online: bool = await redis.exists(f"status:{session_id}")
    except Exception as e:
        logger.error(f"Redis error checking session status for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Redis unavailable")

    if not is_online:
        logger.warning(
            f"Session {session_id} is offline — retrying later "
            f"(content_length={len(str(payload.get('content', '')))})"
        )
        raise HTTPException(
            status_code=503, detail=f"client offline: session_id={session_id}"
        )

    channel_name = f"user_{session_id}"
    try:
        receivers = await redis.publish(
            channel_name, json.dumps({"session_id": session_id, "data": payload})
        )
        logger.info(f"Published to Redis channel {channel_name}. Receivers: {receivers}")
    except Exception as e:
        logger.error(f"Redis publish failed for channel {channel_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to publish to Redis")

    return {"status": "ok"}
