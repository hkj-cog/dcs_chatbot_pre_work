# Pub/Sub push receiver: publishes to Redis for live WS delivery or buffers in inbox:{session_id} for late-connecting WS.
import base64
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from libs.config import get_settings
from libs.redis_manager import get_redis
from libs.ws_connection_manager import ws_manager
from receiver.models import PubSubEnvelope

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()


@router.post("/chat")
async def pubsub_router(envelope: PubSubEnvelope, redis: Redis = Depends(get_redis)):
    # Decodes the Pub/Sub envelope and routes the reply to the live WS or inbox buffer.
    try:
        decoded_str = base64.b64decode(envelope.message.data).decode("utf-8")
        payload = json.loads(decoded_str)
        session_id = envelope.message.attributes.get("session_id")

        if not session_id:
            # Without a session_id we cannot route the reply at all.
            raise HTTPException(status_code=400, detail="missing session_id attribute")

        logger.info(
            f"Pub/Sub received reply: session_id={session_id} "
            f"content_length={len(str(payload.get('content', '')))}"
        )

        redis_payload = {"session_id": session_id, "data": payload}
        serialized = json.dumps(redis_payload)
        channel_name = f"user_{session_id}"
        inbox_key = f"inbox:{session_id}"

        # Always publish — if a subscriber is attached it gets it immediately.
        try:
            receivers = await redis.publish(channel_name, serialized)
        except Exception as e:
            logger.error(f"Error publishing to Redis channel {channel_name}: {e}")
            raise HTTPException(status_code=503, detail=f"redis publish failed: {e}")

        # If no live subscriber and no presence key, the WS hasn't connected yet.
        is_online = await redis.exists(f"status:{session_id}")
        if receivers == 0 and not is_online:
            if not _settings.ws_inbox_enabled:
                logger.warning(
                    f"WS not connected for session_id={session_id} and inbox disabled — "
                    "asking Pub/Sub to retry"
                )
                # 503 → Pub/Sub retries. Avoids silent drops while honouring the kill-switch.
                raise HTTPException(
                    status_code=503,
                    detail=f"ws not connected; inbox disabled (session_id={session_id})",
                )

            ttl = _settings.ws_inbox_ttl_seconds
            cap = _settings.ws_inbox_max_messages
            if cap <= 0:
                logger.warning(
                    f"WS_INBOX_MAX_MESSAGES={cap} — buffering effectively off; "
                    f"asking Pub/Sub to retry for session_id={session_id}"
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"ws not connected; inbox cap<=0 (session_id={session_id})",
                )

            try:
                async with redis.pipeline() as pipe:
                    pipe.rpush(inbox_key, serialized)
                    pipe.ltrim(inbox_key, -cap, -1)   # keep only the newest `cap` entries
                    pipe.expire(inbox_key, ttl)
                    await pipe.execute()
                logger.info(
                    f"WS not yet connected for session_id={session_id} — "
                    f"buffered reply to {inbox_key} (ttl={ttl}s, cap={cap})"
                )
            except Exception as e:
                logger.error(f"Failed to buffer reply for session_id={session_id}: {e}")
                # Tell Pub/Sub to retry rather than silently lose the reply.
                raise HTTPException(status_code=503, detail=f"redis buffer failed: {e}")
        else:
            logger.info(
                f"Published to {channel_name}. live_receivers={receivers} "
                f"online_flag={'yes' if is_online else 'no'}"
            )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        # Returning a non-2xx code tells Pub/Sub to retry later.
        raise HTTPException(status_code=400, detail=f"Invalid message: {str(e)}")


async def process_redis_message(data: str, channel: str):
    """Legacy helper retained for compatibility — used by the WS subscriber path."""
    logger.info(f"Processing Task: {data}")
    session_id = channel.replace("user_", "")
    payload = json.loads(data)
    content = payload.get("data", {})
    await ws_manager.send_personal_message(content, session_id)
    logger.info(f"Message sent to WebSocket for session_id={session_id}")