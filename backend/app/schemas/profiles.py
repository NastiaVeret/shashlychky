from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.recipes import normalize_product_names

# Stable identifiers; the frontend owns the Ukrainian labels.
Diet = Literal[
    "vegetarian", "vegan", "pescatarian", "gluten_free", "lactose_free", "halal", "fasting"
]
Equipment = Literal["oven", "stovetop", "microwave", "multicooker", "air_fryer", "blender"]


class UserProfile(BaseModel):
    """Cooking context of a user. Stored as JSONB on `users.profile`; every field has a default,
    so profiles saved by an older version of this schema still validate."""

    allergies: Annotated[list[str], Field(max_length=20)] = []
    diets: Annotated[list[Diet], Field(max_length=7)] = []
    disliked: Annotated[list[str], Field(max_length=30)] = []
    # Empty means "not specified": the recipe assumes an ordinary kitchen.
    equipment: Annotated[list[Equipment], Field(max_length=6)] = []
    default_servings: Annotated[int, Field(ge=1, le=12)] = 2
    # Products that are always at home (grains, oil, spices); pre-fill the recipe form.
    pantry: Annotated[list[str], Field(max_length=50)] = []

    @field_validator("allergies", "disliked", "pantry")
    @classmethod
    def normalize_products(cls, products: list[str]) -> list[str]:
        return normalize_product_names(products)

    @field_validator("diets", "equipment")
    @classmethod
    def dedupe(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))
