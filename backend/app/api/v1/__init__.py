from fastapi import APIRouter

from app.api.v1 import health, recipes

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(recipes.router)
