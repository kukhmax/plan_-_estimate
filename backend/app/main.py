from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.clients import router as clients_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.rooms import router as rooms_router
from app.api.v1.endpoints.surfaces import router as surfaces_router
from app.core.config import settings

app = FastAPI(
    title="Plan & Estimate API",
    description="Backend API for Telegram Mini App - Renovation & Finishing Management",
    version="0.1.0",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(clients_router, prefix="/api", tags=["clients"])
app.include_router(projects_router, prefix="/api", tags=["projects"])
app.include_router(rooms_router, prefix="/api", tags=["rooms"])
app.include_router(surfaces_router, prefix="/api", tags=["surfaces"])
