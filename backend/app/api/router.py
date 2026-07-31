from fastapi import APIRouter

from app.api import dashboard, scans, settings, suggestions, users

api_router = APIRouter()
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
api_router.include_router(suggestions.router)
api_router.include_router(scans.router)
api_router.include_router(settings.router)

