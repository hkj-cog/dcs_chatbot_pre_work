import json
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    project_id: str = Field(default="my-gcp-project", validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", validation_alias="GOOGLE_CLOUD_LOCATION")
    queue_topic: str = Field(default="my-topic", validation_alias="QUEUE_TOPIC")
    pubsub_emulator_host: str = Field(
        default="", validation_alias="PUBSUB_EMULATOR_HOST"
    )

    redis_host: str = Field(
        default="127.0.0.1:6379", validation_alias="REDIS_HOST"
    )

    allowed_origins: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")

    model_id: str = Field(default="gemini-2.5-flash", validation_alias="MODEL_ID")
    datastore_id: str = Field(default="", validation_alias="DATASTORE_ID")

    pii_data_types: List[str] = Field(
        default=["EMAIL_ADDRESS", "PHONE_NUMBER", "FIRST_NAME", "LAST_NAME"],
        validation_alias="PII_DATA_TYPES",
    )

    @field_validator("pii_data_types", mode="before")
    @classmethod
    def parse_pii_data_types(cls, v):
        """Accept a JSON string from .env or a plain list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """
    Creates a singleton-like instance of settings.
    lru_cache prevents reloading the .env file on every request.
    """
    return Settings()