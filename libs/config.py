import json
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    project_id: str = Field(default="my-gcp-project", validation_alias="PROJECT_ID")
    queue_topic: str = Field(default="my-topic", validation_alias="QUEUE_TOPIC")
    redis_url: str = Field(
        default="redis://localhost:6379/0", validation_alias="REDIS_HOST"
    )
    pubsub_emulator_host: str = Field(
        default="127.0.0.1:8000", validation_alias="PUBSUB_EMULATOR_HOST"
    )
    allowed_origins: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")

    # ── DLP ──────────────────────────────────────────────────────────────────
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