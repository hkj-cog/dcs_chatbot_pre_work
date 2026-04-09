import os
from google.cloud import pubsub_v1
from google.pubsub_v1.types import PushConfig, DeadLetterPolicy, RetryPolicy
from google.protobuf.duration_pb2 import Duration

# 1. Environment Configuration
os.environ["PUBSUB_EMULATOR_HOST"] = "127.0.0.1:8406"

PROJECT_ID = "cog01hygeb83z4tne1xxrhezf82e2"
TOPIC_ID = "adk_chat_messages"
SUB_ID = "adk_chat_messages-sub"
# Dead Letter Topic (required to enforce max attempts)
DLT_TOPIC_ID = "adk_chat_messages-dead-letter"

FASTAPI_ENDPOINT = "http://localhost:8000/webhook/chat"

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
sub_path = subscriber.subscription_path(PROJECT_ID, SUB_ID)
dlt_path = publisher.topic_path(PROJECT_ID, DLT_TOPIC_ID)

print(f"Connecting to Pub/Sub Emulator at: {os.environ['PUBSUB_EMULATOR_HOST']}")

# 2. Create Main Topic & Dead Letter Topic
for path in [topic_path, dlt_path]:
    try:
        publisher.create_topic(request={"name": path})
        print(f"✔ Topic created: {path.split('/')[-1]}")
    except Exception:
        print(f"ℹ Topic exists: {path.split('/')[-1]}")

# 3. Create/Recreate Push Subscription
try:
    # Cleanup old sub if it exists
    try:
        subscriber.delete_subscription(request={"subscription": sub_path})
        print(f"✔ Old subscription deleted.")
    except Exception:
        pass

    # Configuration for the Push endpoint
    push_config = PushConfig(push_endpoint=FASTAPI_ENDPOINT)

    # Configuration to limit retries
    # max_delivery_attempts: must be between 5 and 100 on real GCP.
    # Note: On the emulator, some versions allow as low as 2,
    # but GCP Production requires a minimum of 5.
    dead_letter_policy = DeadLetterPolicy(
        dead_letter_topic=dlt_path, max_delivery_attempts=5
    )

    # Optional: Define how long to wait between those attempts
    retry_policy = RetryPolicy(
        minimum_backoff=Duration(seconds=10), maximum_backoff=Duration(seconds=300)
    )

    subscriber.create_subscription(
        request={
            "name": sub_path,
            "topic": topic_path,
            "push_config": push_config,
            "dead_letter_policy": dead_letter_policy,
            "retry_policy": retry_policy,
        }
    )

    print(f"🚀 Success! Push Subscription created with 5-attempt limit:")
    print(f"    {sub_path} -> {FASTAPI_ENDPOINT}")
    print(f"    Failed messages will move to: {DLT_TOPIC_ID}")

except Exception as e:
    print(f"✘ Failed to create subscription: {e}")
