import asyncio
import json

from google.api_core import client_options
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
    """
    Factory to create a Pub/Sub publisher client.
    Automatically targets the local emulator when PUBSUB_EMULATOR_HOST is set.
    """
    if _emulator_host:
        logger.info(f"Using Pub/Sub Emulator at {_emulator_host}")
        options = client_options.ClientOptions(api_endpoint=_emulator_host)
        return pubsub_v1.PublisherClient(
            client_options=options,
            credentials=None,
        )
        
    batch_settings = pubsub_v1.types.BatchSettings(
        max_bytes=1024 * 1024,  # 1 MB
        max_latency=0.01,       # 10 ms
        max_messages=100,
    )
    return pubsub_v1.PublisherClient(batch_settings=batch_settings)


publisher = create_publisher_client()
TOPIC_PATH = publisher.topic_path(_project_id, _topic)


async def send_message_to_pubsub(message: dict[str, str], session_id: str) -> None:
    """
    Publishes a message to GCP Pub/Sub.

    The session_id is attached as a message attribute so downstream push
    subscriptions (worker/api.py) can route the message to the correct
    WebSocket session without decoding the body.

    Args:
        message:    Payload dict — will be JSON-encoded and base64-wrapped by the SDK.
        session_id: Session identifier; forwarded as a Pub/Sub message attribute.
    """
    try:
        logger.info(
            f"Publishing to Pub/Sub: topic={TOPIC_PATH} "
            f"session_id={session_id} payload={message}"
        )
        data = json.dumps(message).encode("utf-8")

        custom_retry = retries.Retry(
            initial=0.1,    # first back-off: 100 ms
            maximum=60.0,   # cap at 60 s
            multiplier=1.3,
        )

        publish_future: Future = publisher.publish(
            TOPIC_PATH,
            data,
            session_id=session_id,  # passed as a message attribute for filtering
            retry=custom_retry,
        )

        # Resolve the future without blocking the asyncio event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, publish_future.result)

        logger.info(
            f"Published to {TOPIC_PATH} — "
            f"session_id={session_id} message_id={result}"
        )
    except Exception as e:
        logger.error(f"Failed to publish message to Pub/Sub: {e}")
        raise