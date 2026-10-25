from typing import Annotated

from fastapi import APIRouter, Query, status

from app.db.session import DbSession
from app.models.recipe import Recipe
from app.schemas.nutrition import MAX_DAILY_KCAL, MIN_DAILY_KCAL, RecipeNutrition
from app.schemas.recipes import RecipeContent, RecipeRead, RecipeRequest
from app.services import nutrition as nutrition_service
from app.services import recipes as service
from app.services.llm import LLMDep
from app.services.nutrition import NutritionDep

router = APIRouter(prefix="/recipes", tags=["recipes"])


def to_read(recipe: Recipe) -> RecipeRead:
    content = RecipeContent.model_validate(recipe.content)
    return RecipeRead(
        id=recipe.id,
        products=recipe.products,
        created_at=recipe.created_at,
        **content.model_dump(),
    )


@router.post("", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
async def create_recipe(req: RecipeRequest, db: DbSession, llm: LLMDep) -> RecipeRead:
    """Generate a recipe from the user's products and store it."""
    recipe = await service.generate_recipe(db, llm, req)
    await db.commit()
    await db.refresh(recipe)
    return to_read(recipe)


@router.get("/{recipe_id}", response_model=RecipeRead)
async def read_recipe(recipe_id: int, db: DbSession) -> RecipeRead:
    return to_read(await service.get_recipe(db, recipe_id))


@router.get("/{recipe_id}/nutrition", response_model=RecipeNutrition)
async def read_recipe_nutrition(
    recipe_id: int,
    db: DbSession,
    provider: NutritionDep,
    daily_kcal_goal: Annotated[int | None, Query(ge=MIN_DAILY_KCAL, le=MAX_DAILY_KCAL)] = None,
) -> RecipeNutrition:
    """Calories and macros of a stored recipe from Silpo product data, optionally vs a goal."""
    return await nutrition_service.recipe_nutrition(db, provider, recipe_id, daily_kcal_goal)
