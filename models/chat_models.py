from typing import List, Optional
from pydantic import BaseModel, Field

class Reference(BaseModel):
    chunk: str = ""
    url: str = ""
    title: str = ""

class ChatResponse(BaseModel):
    sender: str
    content: str
    session_id: str
    references: List[Reference] = Field(default_factory=list)
    score: Optional[str] = None