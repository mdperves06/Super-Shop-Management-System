from fastapi import APIRouter

from app.api.v1 import auth, catalog, inventory, system, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, catalog, inventory, system):
    api_router.include_router(module.router)
