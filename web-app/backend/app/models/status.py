from typing import List, Literal, Optional

from pydantic import BaseModel


class StatusResponse(BaseModel):
    connected: bool
    database: Optional[str] = None        # the active database's name (knowledge/<name>/)
    databases: List[str] = []             # every saved database
    provider: Optional[str] = None
    audited: bool
    database_mismatch: Optional[str] = None
    agent_available: bool
    mode: Literal["agent", "simulated"]
