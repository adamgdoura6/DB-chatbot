from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(max_length=8000)
    # The agent session to continue; returned by the first reply as {"type": "conversation"}
    conversation: Optional[str] = None
