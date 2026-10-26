from fastapi import APIRouter

from app.models.status import StatusResponse
from app.services.status import get_status

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("", response_model=StatusResponse)
def status():
    """Whether a database is connected and audited, and which chat answers."""
    return get_status()
