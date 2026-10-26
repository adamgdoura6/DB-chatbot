from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    # API Configuration
    API_TITLE: str = "DB-chatbot web API"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = "Backend for the DB-chatbot web app: connect a database, run the audit, talk to it"

    # Chat mode: "auto" (the real agent once a database is connected, otherwise simulated),
    # "agent" (always the real agent) or "simulated" (always canned replies)
    WEBAPP_MODE: str = "auto"

    # Repository root: knowledge/, shared/dbq.py, audit-your-database/ and the .env
    # that holds the database connection
    REPO_ROOT: Path = Path(__file__).resolve().parents[3]

    # CORS: the Next.js dev server proxies /api, so this only matters when calling the API directly
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def DATABASE_ENV_FILE(self) -> Path:
        return self.REPO_ROOT / ".env"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Create settings instance
settings = Settings()
