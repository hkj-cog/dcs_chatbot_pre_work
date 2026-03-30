import os

from google.cloud import pubsub_v1
from google.pubsub_v1.types import PushConfig

# 1. Environment Configuration
# Ensure this matches your emulator's actual port
os.environ["PUBSUB_EMULATOR_HOST"] = "127.0.0.1:8406"

PROJECT_ID = "cog01hygeb83z4tne1xxrhezf82e2"
TOPIC_ID = "adk_chat_messages"
SUB_ID = "adk_chat_messages-sub"

# Ensure this matches your FastAPI host/port and the specific endpoint
FASTAPI_ENDPOINT = "http://localhost:8000/webhook/chat"

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
sub_path = subscriber.subscription_path(PROJECT_ID, SUB_ID)

print(f"Connecting to Pub/Sub Emulator at: {os.environ['PUBSUB_EMULATOR_HOST']}")

# 2. Create Topic
try:
    publisher.create_topic(request={"name": topic_path})
    print(f"✔ Topic created: {TOPIC_ID}")
except Exception as e:
    print(f"ℹ Topic exists or was skipped: {e}")

# 3. Create/Recreate Push Subscription
# We delete and recreate to ensure the push_config is applied correctly
try:
    try:
        subscriber.delete_subscription(request={"subscription": sub_path})
        print(f"✔ Old subscription deleted.")
    except Exception:
        pass

    # Define the push configuration
    push_config = PushConfig(push_endpoint=FASTAPI_ENDPOINT)

    subscriber.create_subscription(
        request={
            "name": sub_path,
            "topic": topic_path,
            "push_config": push_config,
        }
    )
    print(f"🚀 Success! Push Subscription created:")
    print(f"   {sub_path} -> {FASTAPI_ENDPOINT}")

except Exception as e:
    print(f"✘ Failed to create subscription: {e}")


# 4. Optional: Quick Test Publish
def test_publish():
    print("\nSending test message...")
    data = "Hello FastAPI!".encode("utf-8")
    future = publisher.publish(topic_path, data)
    print(f"Message ID: {future.result()}")


if __name__ == "__main__":
    test_publish()
