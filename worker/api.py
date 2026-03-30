import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Response
from fastapi.requests import Request
import base64
import json

from redis.asyncio import Redis

from libs.redis_manager import get_redis
from libs.ws_connection_manager import ws_manager
from models.chat_models import ChatResponse
from receiver.models import PubSubEnvelope

router = APIRouter()

# Setup basic logging so you can see the worker's heartbeat in Cloud Run logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/chat")
async def pubsub_router(envelope: PubSubEnvelope, redis: Redis = Depends(get_redis)):
    try:
        base64_data = envelope.message.data

        decoded_bytes = base64.b64decode(base64_data)
        decoded_str = decoded_bytes.decode("utf-8")

        payload = json.loads(decoded_str)
        session_id = envelope.message.attributes.get("session_id")
        logger.info(
            f"Received Pub/Sub message with ID: {payload}, session_id={session_id}"
        )

        is_online: bool = await redis.exists(f"status:{session_id}")

        if not is_online:
            logger.warning(
                f"Session {session_id} is offline. Message will be discarded: {payload}"
            )
            raise HTTPException(
                status_code=400, detail=f"client is offline: session_id={session_id}"
            )

        redis_payload = {"session_id": session_id, "data": payload}

        channel_name = f"user_{session_id}"

        try:
            receivers = await redis.publish(channel_name, json.dumps(redis_payload))
            logger.info(
                f"Published message to Redis channel {channel_name}. Receivers: {receivers}"
            )
        except Exception as e:
            logger.error(f"Error publishing to Redis channel {channel_name}: {e}")
            raise e
        return {"status": "ok"}

    except Exception as e:
        # Returning a non-2xx code tells Pub/Sub to retry later
        raise HTTPException(status_code=400, detail=f"Invalid message: {str(e)}")


async def process_redis_message(data: str, channel: str):
    logger.info(f"Processing Task: {data}")
    session_id = channel.replace("user_", "")

    payload = json.loads(data)
    content = payload.get("data", {})
    await ws_manager.send_personal_message(content, session_id)
    logger.info(f"Message sent to WebSocket for session_id={session_id}: {content}")
