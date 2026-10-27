from typing import Literal

from pydantic import BaseModel, Field

MIN_DAILY_KCAL = 800
MAX_DAILY_KCAL = 6000

# counted: product found in Silpo, has nutrition data and the quantity converts to grams
# to_taste: no quantity in the recipe ("за смаком"), nothing to count
# no_product: Silpo found no available product for the ingredient
# no_data: the product card has no calories / macros
# unknown_unit: the quantity cannot be converted to grams (e.g. "шт" of a pack of 10)
IngredientStatus = Literal["counted", "to_taste", "no_product", "no_data", "unknown_unit"]


class NutritionFacts(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float


class IngredientNutrition(BaseModel):
    name: str
    status: IngredientStatus
    grams: float | None = Field(description="Вага інгредієнта в рецепті, якщо її вдалося визначити")
    product_name: str | None = Field(description="Товар Сільпо, з якого взято КБЖВ")
    per_100g: NutritionFacts | None
    total: NutritionFacts | None


class GoalComparison(BaseModel):
    daily_kcal: int
    per_serving_percent: float = Field(description="Яку частку денної норми покриває одна порція")


class RecipeNutrition(BaseModel):
    recipe_id: int
    servings: int
    total: NutritionFacts
    per_serving: NutritionFacts
    counted_ingredients: int
    countable_ingredients: int = Field(description="Інгредієнти з кількістю (без 'за смаком')")
    ingredients: list[IngredientNutrition]
    goal: GoalComparison | None
