from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PRODUCTS = 30
MAX_PRODUCT_LEN = 40


class RecipeRequest(BaseModel):
    products: Annotated[list[str], Field(min_length=1, max_length=MAX_PRODUCTS)]
    preferences: Annotated[str | None, Field(max_length=200)] = None
    servings: Annotated[int, Field(ge=1, le=12)] = 2

    @field_validator("products")
    @classmethod
    def normalize_products(cls, products: list[str]) -> list[str]:
        """Trim, drop empties, cap length, de-duplicate case-insensitively, keep order."""
        seen: set[str] = set()
        result: list[str] = []
        for raw in products:
            name = " ".join(raw.split())[:MAX_PRODUCT_LEN]
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                result.append(name)
        if not result:
            raise ValueError("Потрібен хоча б один продукт")
        return result


class Ingredient(BaseModel):
    name: str = Field(description="Назва інгредієнта українською")
    quantity: float | None = Field(default=None, description="Кількість; null, якщо 'за смаком'")
    unit: str = Field(description="Одиниця: г, мл, шт, ст. л., ч. л. або 'за смаком'")
    have_at_home: bool = Field(
        description=(
            "true, якщо інгредієнт є серед продуктів користувача або базовий (сіль, вода, олія)"
        )
    )


class RecipeContent(BaseModel):
    """What the model must return. Also the stored recipe body."""

    title: str = Field(description="Назва страви")
    description: str = Field(description="1-2 речення про страву")
    cooking_time_minutes: int = Field(ge=1, le=600)
    servings: int = Field(ge=1, le=12)
    ingredients: list[Ingredient] = Field(min_length=1)
    steps: list[str] = Field(min_length=1, description="Кроки приготування по порядку")
    tips: str | None = Field(default=None, description="Коротка порада або варіант заміни")
    clarifying_question: str | None = Field(
        default=None,
        description=(
            "Якщо з наданих продуктів неможливо зібрати страву або продукт незрозумілий, "
            "постав тут одне уточнювальне питання; інакше null"
        ),
    )


class RecipeRead(RecipeContent):
    model_config = ConfigDict(from_attributes=True)

    id: int
    products: list[str]
    created_at: datetime
