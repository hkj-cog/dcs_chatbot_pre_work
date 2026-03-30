from functools import lru_cache
from typing import final
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Automatically reads APP_PORT from environment or .env
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """
    Creates a singleton-like instance of settings.
    lru_cache prevents reloading the .env file on every request.
    """
    return Settings()
