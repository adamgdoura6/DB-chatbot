import json
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest
from app.services import agent, simulated
from app.services.status import chat_mode

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
def chat(body: ChatRequest):
    """
    Stream the reply as one JSON object per line:
    {"type": "conversation", "id"}, {"type": "text", "text": "word "} ...,
    then {"type": "details", "sql", "tables", "note"} or {"type": "error", "text"}.
    """
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "message required")
    run = agent.chat if chat_mode() == "agent" else simulated.chat

    def lines() -> Iterator[str]:
        for part in run(message, body.conversation):
            yield json.dumps(part, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")
