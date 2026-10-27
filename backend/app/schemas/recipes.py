"""Request and response models for recipe generation.

`RecipeContent` is the strict contract the LLM must satisfy: normalized units and a step-by-step
method. Anything the model gets slightly wrong in a harmless way (a unit spelled differently,
kilograms instead of grams, numbered steps) is normalized here instead of costing a corrective
retry; anything genuinely wrong fails validation and the LLM client asks the model to fix it.

Nutrition (КБЖВ) is deliberately not here: it is computed from real product data by the
nutrition service, not estimated by the model.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from app.models.recipe import Recipe as RecipeModel

MAX_PRODUCTS = 30
MAX_PRODUCT_LEN = 40
MAX_INGREDIENTS = 25
MAX_STEPS = 20
MAX_STEP_LEN = 300


class Unit(StrEnum):
    """Normalized measurement units. The model may not invent any others."""

    GRAM = "г"
    MILLILITER = "мл"
    PIECE = "шт"
    TABLESPOON = "ст. л."
    TEASPOON = "ч. л."
    TO_TASTE = "за смаком"


UNITS_HINT = ", ".join(u.value for u in Unit)

# Spellings mapped onto `Unit` as-is. Keys are unit names with everything but letters and digits
# removed, so "ст. л.", "ст.л." and "ст л" all arrive here as "стл".
_UNIT_ALIASES: dict[str, Unit] = {
    "г": Unit.GRAM,
    "гр": Unit.GRAM,
    "грам": Unit.GRAM,
    "грами": Unit.GRAM,
    "грамів": Unit.GRAM,
    "g": Unit.GRAM,
    "мл": Unit.MILLILITER,
    "мілілітр": Unit.MILLILITER,
    "мілілітри": Unit.MILLILITER,
    "мілілітрів": Unit.MILLILITER,
    "ml": Unit.MILLILITER,
    "шт": Unit.PIECE,
    "штука": Unit.PIECE,
    "штуки": Unit.PIECE,
    "штук": Unit.PIECE,
    "pcs": Unit.PIECE,
    "зубчик": Unit.PIECE,
    "зубчики": Unit.PIECE,
    "зубчиків": Unit.PIECE,
    "зубок": Unit.PIECE,
    "зубки": Unit.PIECE,
    "головка": Unit.PIECE,
    "головки": Unit.PIECE,
    "пучок": Unit.PIECE,
    "пучки": Unit.PIECE,
    "пучків": Unit.PIECE,
    "стл": Unit.TABLESPOON,
    "стложка": Unit.TABLESPOON,
    "столоваложка": Unit.TABLESPOON,
    "столовіложки": Unit.TABLESPOON,
    "столовихложок": Unit.TABLESPOON,
    "столовоїложки": Unit.TABLESPOON,
    "стложки": Unit.TABLESPOON,
    "стложок": Unit.TABLESPOON,
    "tbsp": Unit.TABLESPOON,
    "чл": Unit.TEASPOON,
    "чложка": Unit.TEASPOON,
    "чайналожка": Unit.TEASPOON,
    "чайніложки": Unit.TEASPOON,
    "чайнихложок": Unit.TEASPOON,
    "чайноїложки": Unit.TEASPOON,
    "чложки": Unit.TEASPOON,
    "чложок": Unit.TEASPOON,
    "tsp": Unit.TEASPOON,
    "засмаком": Unit.TO_TASTE,
    "досмаку": Unit.TO_TASTE,
    "посмаку": Unit.TO_TASTE,
    "насмак": Unit.TO_TASTE,
    "щіпка": Unit.TO_TASTE,
    "щіпки": Unit.TO_TASTE,
}

# Units that carry a different scale: the quantity is converted along with the unit.
_SCALED_UNITS: dict[str, tuple[Unit, float]] = {
    "кг": (Unit.GRAM, 1000),
    "кілограм": (Unit.GRAM, 1000),
    "кілограми": (Unit.GRAM, 1000),
    "кілограмів": (Unit.GRAM, 1000),
    "kg": (Unit.GRAM, 1000),
    "л": (Unit.MILLILITER, 1000),
    "літр": (Unit.MILLILITER, 1000),
    "літри": (Unit.MILLILITER, 1000),
    "літрів": (Unit.MILLILITER, 1000),
    "l": (Unit.MILLILITER, 1000),
    # A Ukrainian cooking glass is 250 ml.
    "склянка": (Unit.MILLILITER, 250),
    "склянки": (Unit.MILLILITER, 250),
    "склянок": (Unit.MILLILITER, 250),
    "стакан": (Unit.MILLILITER, 250),
    "стакани": (Unit.MILLILITER, 250),
    "стаканів": (Unit.MILLILITER, 250),
    "чашка": (Unit.MILLILITER, 250),
    "чашки": (Unit.MILLILITER, 250),
}

_STEP_NUMBERING = re.compile(r"^\s*\d{1,2}[.)]\s+")


def _unit_key(raw: str) -> str:
    """Fold a written unit to its comparable form: lowercase letters and digits only."""
    return "".join(ch for ch in raw.casefold() if ch.isalnum())


def normalize_product_names(products: list[str]) -> list[str]:
    """Trim, drop empties, cap length, de-duplicate case-insensitively, keep order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in products:
        name = " ".join(raw.split())[:MAX_PRODUCT_LEN]
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


class RecipeRequest(BaseModel):
    products: Annotated[list[str], Field(min_length=1, max_length=MAX_PRODUCTS)]
    preferences: Annotated[str | None, Field(max_length=200)] = None
    servings: Annotated[int, Field(ge=1, le=12)] = 2

    @field_validator("products")
    @classmethod
    def normalize_products(cls, products: list[str]) -> list[str]:
        result = normalize_product_names(products)
        if not result:
            raise ValueError("Потрібен хоча б один продукт")
        return result


class Ingredient(BaseModel):
    name: str = Field(
        min_length=1, max_length=60, description="Назва інгредієнта українською, без кількості"
    )
    quantity: float | None = Field(
        default=None, ge=0, le=100_000, description="Кількість; null, якщо 'за смаком'"
    )
    unit: Unit = Field(description=f"Одиниця виміру, строго одна з: {UNITS_HINT}")
    have_at_home: bool = Field(
        description=(
            "true, якщо інгредієнт є серед продуктів користувача або базовий (сіль, вода, олія)"
        )
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_measurement(cls, data: Any) -> Any:  # noqa: ANN401 - raw input of any shape
        """Fold a free-form unit onto `Unit`, converting the quantity when the scale differs."""
        if not isinstance(data, dict):
            return data
        raw_unit = data.get("unit")
        if not isinstance(raw_unit, str):
            return data

        quantity = data.get("quantity")
        if isinstance(quantity, bool):
            raise ValueError("Кількість має бути числом, не true/false")
        amount: float | None = (
            float(quantity)
            if isinstance(quantity, int | float) and not isinstance(quantity, bool)
            else None
        )

        key = _unit_key(raw_unit)
        if scaled := _SCALED_UNITS.get(key):
            unit, factor = scaled
            if amount is not None:
                quantity = round(amount * factor, 2)
        elif alias := _UNIT_ALIASES.get(key):
            unit = alias
        else:
            raise ValueError(f"Невідома одиниця '{raw_unit}'. Дозволені лише: {UNITS_HINT}")

        if amount is not None and amount <= 0:
            quantity = None
        # Anything else (a numeric string, None) is left for Pydantic to coerce or reject.
        return {**data, "unit": unit, "quantity": quantity}

    @model_validator(mode="after")
    def reconcile_quantity(self) -> Self:
        """A measurable unit needs a number, and 'за смаком' must not carry one."""
        if self.unit is Unit.TO_TASTE:
            self.quantity = None
        elif self.quantity is None:
            self.unit = Unit.TO_TASTE
        return self


class RecipeContent(BaseModel):
    """What the model must return. Also the stored recipe body."""

    title: str = Field(min_length=1, max_length=80, description="Назва страви")
    description: str = Field(min_length=1, max_length=300, description="1-2 речення про страву")
    cooking_time_minutes: int = Field(ge=1, le=600)
    servings: int = Field(ge=1, le=12)
    ingredients: list[Ingredient] = Field(min_length=1, max_length=MAX_INGREDIENTS)
    steps: list[Annotated[str, Field(max_length=MAX_STEP_LEN)]] = Field(
        min_length=1,
        max_length=MAX_STEPS,
        description="Кроки приготування по порядку, одна дія на крок, без нумерації",
    )
    tips: str | None = Field(default=None, max_length=300, description="Порада або варіант заміни")
    clarifying_question: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Якщо з наданих продуктів неможливо зібрати страву або продукт незрозумілий, "
            "постав тут одне уточнювальне питання; інакше null"
        ),
    )

    @field_validator("steps")
    @classmethod
    def normalize_steps(cls, steps: list[str]) -> list[str]:
        """Collapse whitespace, strip the model's own numbering, drop empties."""
        result = [" ".join(_STEP_NUMBERING.sub("", step).split()) for step in steps]
        cleaned = [step for step in result if step]
        if not cleaned:
            raise ValueError("Рецепт має містити хоча б один крок")
        return cleaned


class IngredientRead(BaseModel):
    """An ingredient as stored. `unit` is free text here: rows written before the `Unit` enum
    existed keep whatever the model said back then ("зубчики", "пучок") and must stay readable."""

    name: str
    quantity: float | None = None
    unit: str
    have_at_home: bool = True


class RecipeRead(BaseModel):
    """API response for a stored recipe. Deliberately lenient: the strict bounds in
    `RecipeContent` are the contract for *generation*; a recipe that was valid when it was
    saved must never turn into a 500 because the contract got stricter later."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    products: list[str]
    created_at: datetime
    title: str
    description: str
    cooking_time_minutes: int
    servings: int
    ingredients: list[IngredientRead]
    steps: list[str]
    tips: str | None = None
    clarifying_question: str | None = None

    @classmethod
    def from_model(cls, recipe: "RecipeModel") -> "RecipeRead":
        return cls.model_validate(
            {
                **recipe.content,
                "id": recipe.id,
                "products": recipe.products,
                "created_at": recipe.created_at,
            }
        )
