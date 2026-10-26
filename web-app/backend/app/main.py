from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, connection, health, status

app = FastAPI(title=settings.API_TITLE,
              version=settings.API_VERSION,
              description=settings.API_DESCRIPTION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(status.router)
app.include_router(chat.router)
app.include_router(connection.router)
