from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_input: str


class PubSubMessage(BaseModel):
    data: str
    messageId: str
    publishTime: str
    attributes: dict[str, str] = {}


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str
