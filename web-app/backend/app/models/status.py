from typing import Literal, Optional

from pydantic import BaseModel


class StatusResponse(BaseModel):
    connected: bool
    provider: Optional[str] = None
    audited: bool
    agent_available: bool
    mode: Literal["agent", "simulated"]
