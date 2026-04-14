import asyncio
import json
import os

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher.futures import Future
from google.api_core import client_options
from libs.config import Settings
from libs.logger import logger
from google.api_core import retry as retries

settings = Settings()
publisher = pubsub_v1.PublisherClient()
project_id = settings.GOOGLE_CLOUD_PROJECT
topic = settings.queue_topic
emulator_host = settings.pubsub_emulator_host


def create_publisher_client() -> pubsub_v1.PublisherClient:
    """
    Factory to create a client that automatically detects the emulator.
    """
    if emulator_host != "":
        logger.info(f"Using Pub/Sub Emulator at {emulator_host}")
        options = client_options.ClientOptions(api_endpoint=emulator_host)
        return pubsub_v1.PublisherClient(
            client_options=options,
            credentials=None,  # No auth needed for emulator
        )
    batch_settings = pubsub_v1.types.BatchSettings(
        max_bytes=1024 * 1024,  # 1MB
        max_latency=0.01,  # 10ms
        max_messages=100,
    )
    return pubsub_v1.PublisherClient(batch_settings=batch_settings)


publisher = create_publisher_client()
TOPIC_PATH = publisher.topic_path(settings.GOOGLE_CLOUD_PROJECT, settings.queue_topic)


async def send_message_to_pubsub(message: dict[str, str], session_id: str):
    """
    Publishes a message to GCP Pub/Sub with an Ordering Key.
    """
    try:
        logger.info(
            f"Preparing to publish message to Pub/Sub: {message} with session_id={session_id}, topic={TOPIC_PATH}"
        )
        data = json.dumps(message).encode("utf-8")

        loop = asyncio.get_event_loop()

        custom_retry = retries.Retry(
            initial=0.1,  # seconds
            maximum=60.0,  # total time to keep retrying
            multiplier=1.3,
        )

        publish_future: Future = publisher.publish(
            TOPIC_PATH,
            data,
            session_id=session_id,  # Also sent as an attribute for easy filtering
            retry=custom_retry,
        )

        # 4. Wait for the result without blocking the event loop
        result = await loop.run_in_executor(None, publish_future.result)

        logger.info(
            f"Message published to {TOPIC_PATH} with session_id={session_id}, message_id={result}"
        )
    except Exception as e:
        logger.error(f"Failed to publish message to Pub/Sub: {e}")
        raise e
