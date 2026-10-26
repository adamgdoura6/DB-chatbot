from app.config import settings
from app.services import agent
from app.services.connection import cli

dbq = cli.shared_dbq  # the active database, its connection and folders: repository root .env + knowledge/<name>/


def chat_mode() -> str:
    """Which chat answers: re-read on every message, so connecting switches it without a restart."""
    if settings.WEBAPP_MODE in ("agent", "simulated"):
        return settings.WEBAPP_MODE
    connected = bool(cli.configured_url())
    return "agent" if connected and agent.available() else "simulated"


def get_status() -> dict:
    name = dbq.active_database()
    url = cli.configured_url(name)
    return {
        "connected": bool(url),
        "database": name,
        "databases": dbq.saved_databases(),
        "provider": dbq.read_env().get(dbq.provider_key(name)) if name else None,
        "audited": bool(name) and cli.audited(name),
        # set when knowledge/<name>/ is the audit of another database: shared/dbq.py refuses every query then
        "database_mismatch": dbq.mismatch(name, url) if name and url else None,
        "agent_available": agent.available(),
        "mode": chat_mode(),
    }
