from fastapi import APIRouter

from app.api.v1 import auth, catalog, customers, inventory, purchasing, sales, system, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, catalog, inventory, purchasing, customers, sales, system):
    api_router.include_router(module.router)
