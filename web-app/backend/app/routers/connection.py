from fastapi import APIRouter

from app.models.connection import ConnectRequest, ConnectResponse
from app.services.connection import connect

router = APIRouter(prefix="/api/connect", tags=["connection"])


@router.post("", response_model=ConnectResponse, response_model_exclude_none=True)
def connect_database(body: ConnectRequest):
    """One step of /connect; the response says what is needed next (see services/connection.py)."""
    return connect(body.provider, body.url, body.password, body.force, body.name)
