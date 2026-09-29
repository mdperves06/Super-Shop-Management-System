from fastapi import APIRouter

from app.api.v1 import admin, analytics, auth, catalog, customers, documents, hr, inventory, purchasing, sales, system, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, catalog, inventory, purchasing, customers, sales, hr, analytics, documents, admin, system):
    api_router.include_router(module.router)
