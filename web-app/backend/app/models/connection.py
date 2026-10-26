from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    provider: str = "supabase"
    url: str = Field(max_length=2000)
    password: Optional[str] = Field(default=None, max_length=500)
    # The database's name (knowledge/<name>/); derived from the URL when not given
    name: Optional[str] = Field(default=None, max_length=63)
    # Connect even with an owner/admin login (after the page asked "connect anyway?")
    force: bool = False


class ConnectResponse(BaseModel):
    status: Literal["need_password", "invalid", "unsupported", "risky", "failed", "connected"]
    name: Optional[str] = None           # connected: saved under this name, now the active database
    error: Optional[str] = None          # invalid, failed
    hint: Optional[str] = None           # failed: a likely fix
    reason: Optional[str] = None         # risky
    provider: Optional[str] = None       # unsupported, connected
    db: Optional[str] = None             # connected
    login: Optional[str] = None
    version: Optional[str] = None
    problems: Optional[List[str]] = None  # what the login can do beyond reading
    readable_tables: Optional[int] = None
    privilege_error: Optional[str] = None
