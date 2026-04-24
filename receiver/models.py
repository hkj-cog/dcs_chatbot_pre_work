# Pydantic request models for incoming chat messages and Pub/Sub push envelopes
from pydantic import BaseModel, field_validator


class ChatRequest(BaseModel):
    user_input: str
    translate: bool = False

    # Rejects blank inputs and enforces the MAX_INPUT_CHARS boundary at the HTTP layer
    @field_validator("user_input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        from libs.config import get_settings
        if not v.strip():
            raise ValueError("user_input must not be empty or whitespace")
        # Must match InputLengthGuardRail to reject oversized messages before DLP and task dispatch.
        max_chars = get_settings().max_input_chars
        if len(v) > max_chars:
            raise ValueError(f"user_input exceeds maximum allowed length of {max_chars} characters")
        return v.strip()


class PubSubMessage(BaseModel):
    data: str
    messageId: str
    publishTime: str
    attributes: dict[str, str] = {}


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str
