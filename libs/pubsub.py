# Google Cloud Pub/Sub publisher with retry/backoff and local emulator support
import asyncio
import json
import os

from google.api_core import retry as retries
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher.futures import Future

from libs.config import get_settings
from libs.logger import logger

settings = get_settings()
_project_id = settings.project_id
_topic = settings.queue_topic
_emulator_host = settings.pubsub_emulator_host


def create_publisher_client() -> pubsub_v1.PublisherClient:
    """Creates a Pub/Sub publisher client, targeting the local emulator when PUBSUB_EMULATOR_HOST is set."""
    if _emulator_host:
        # Must set the env var so the SDK uses an insecure gRPC channel (emulator has no TLS).
        os.environ["PUBSUB_EMULATOR_HOST"] = _emulator_host
        logger.info(f"Using Pub/Sub Emulator at {_emulator_host}")
        return pubsub_v1.PublisherClient()

    batch_settings = pubsub_v1.types.BatchSettings(
        max_bytes=1024 * 1024,  # 1 MB
        max_latency=0.01,       # 10 ms
        max_messages=100,
    )
    return pubsub_v1.PublisherClient(batch_settings=batch_settings)


# Lazy init — avoids opening a GCP connection at import time.
_publisher = None
_topic_path = None


# Lazy singleton: creates the publisher client and topic path on first call
def _get_publisher():
    global _publisher, _topic_path
    if _publisher is None:
        _publisher = create_publisher_client()
        _topic_path = _publisher.topic_path(_project_id, _topic)
    return _publisher, _topic_path


async def send_message_to_pubsub(message: dict[str, str], session_id: str) -> None:
    """Publishes `message` to Pub/Sub. session_id is attached as a message attribute for routing."""
    pub, topic_path = _get_publisher()
    try:
        logger.info(
            f"Publishing to Pub/Sub: topic={topic_path} session_id={session_id} "
            f"content_length={len(str(message.get('content', '')))} "
            f"score={message.get('score')} refs={len(message.get('references', []))}"
        )
        data = json.dumps(message).encode("utf-8")

        custom_retry = retries.Retry(
            initial=0.1,    # first back-off: 100 ms
            maximum=60.0,   # cap at 60 s
            multiplier=1.3,
        )

        publish_future: Future = pub.publish(
            topic_path,
            data,
            session_id=session_id,  # passed as a message attribute for filtering
            retry=custom_retry,
        )

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: publish_future.result(timeout=30)
        )

        logger.info(
            f"Published to {topic_path} — "
            f"session_id={session_id} message_id={result}"
        )
    except Exception as e:
        logger.error(f"Failed to publish message to Pub/Sub: {e}")
        raise