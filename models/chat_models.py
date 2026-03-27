from pydantic import BaseModel


class ChatResponse(BaseModel):
    sender: str
    content: str
    session_id: str
