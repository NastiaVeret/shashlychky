"""The contract the LLM has to satisfy: normalized units and clean, ordered steps."""

import pytest
from pydantic import ValidationError

from app.schemas.recipes import Ingredient, RecipeContent, Unit
from tests.conftest import SAMPLE_RECIPE


def _ingredient(**overrides: object) -> Ingredient:
    data: dict[str, object] = {
        "name": "Борошно",
        "quantity": 200,
        "unit": "г",
        "have_at_home": True,
    }
    return Ingredient.model_validate(data | overrides)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("г", Unit.GRAM),
        ("гр.", Unit.GRAM),
        ("грамів", Unit.GRAM),
        ("мл", Unit.MILLILITER),
        ("штук", Unit.PIECE),
        ("ст.л.", Unit.TABLESPOON),
        ("столова ложка", Unit.TABLESPOON),
        ("ч. л.", Unit.TEASPOON),
        ("до смаку", Unit.TO_TASTE),
    ],
)
def test_unit_spellings_fold_to_the_canonical_unit(written: str, expected: Unit) -> None:
    assert _ingredient(unit=written).unit is expected


@pytest.mark.parametrize(
    ("written", "quantity", "expected_unit", "expected_quantity"),
    [
        ("кг", 1.5, Unit.GRAM, 1500),
        ("л", 2, Unit.MILLILITER, 2000),
        ("склянка", 1, Unit.MILLILITER, 250),
        ("склянки", 0.5, Unit.MILLILITER, 125),
    ],
)
def test_bigger_units_are_converted_with_the_quantity(
    written: str, quantity: float, expected_unit: Unit, expected_quantity: float
) -> None:
    ingredient = _ingredient(unit=written, quantity=quantity)
    assert ingredient.unit is expected_unit
    assert ingredient.quantity == expected_quantity


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Невідома одиниця"):
        _ingredient(unit="жменя")


def test_to_taste_ingredient_carries_no_quantity() -> None:
    assert _ingredient(unit="за смаком", quantity=2).quantity is None


def test_measurable_unit_without_a_quantity_becomes_to_taste() -> None:
    # "сіль: г" renders as nonsense; "за смаком" is what the model meant.
    ingredient = _ingredient(name="Сіль", unit="г", quantity=None)
    assert ingredient.unit is Unit.TO_TASTE
    assert ingredient.quantity is None


def test_zero_quantity_becomes_to_taste() -> None:
    assert _ingredient(quantity=0).unit is Unit.TO_TASTE


def test_steps_lose_the_models_own_numbering_and_extra_whitespace() -> None:
    recipe = SAMPLE_RECIPE.model_copy(
        update={"steps": ["1. Збити яйця.", "2)  Смажити   5 хвилин.", "   "]}
    )
    cleaned = RecipeContent.model_validate(recipe.model_dump())
    assert cleaned.steps == ["Збити яйця.", "Смажити 5 хвилин."]


def test_recipe_without_any_usable_step_is_rejected() -> None:
    with pytest.raises(ValidationError, match="хоча б один крок"):
        RecipeContent.model_validate(SAMPLE_RECIPE.model_dump() | {"steps": ["  ", ""]})


def test_generated_recipe_survives_a_json_round_trip() -> None:
    # The content column stores JSON; units must come back as units, not free text.
    stored = SAMPLE_RECIPE.model_dump(mode="json")
    assert stored["ingredients"][0]["unit"] == "шт"
    assert RecipeContent.model_validate(stored).ingredients[0].unit is Unit.PIECE
