from typing import Dict

from app.config import settings
from app.services import agent


def read_database_env() -> Dict[str, str]:
    """The repository root .env: DBCHAT_PROVIDER, DBCHAT_DATABASE_URL, DBCHAT_TENANT."""
    env = {}
    path = settings.DATABASE_ENV_FILE
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                env[key.strip()] = value.strip()
    return env


def chat_mode() -> str:
    """Which chat answers: re-read on every message, so connecting switches it without a restart."""
    if settings.WEBAPP_MODE in ("agent", "simulated"):
        return settings.WEBAPP_MODE
    connected = bool(read_database_env().get("DBCHAT_DATABASE_URL"))
    return "agent" if connected and agent.available() else "simulated"


def get_status() -> dict:
    env = read_database_env()
    return {
        "connected": bool(env.get("DBCHAT_DATABASE_URL")),
        "provider": env.get("DBCHAT_PROVIDER") or None,
        "audited": (settings.REPO_ROOT / "knowledge" / "overview.md").exists(),
        "agent_available": agent.available(),
        "mode": chat_mode(),
    }
