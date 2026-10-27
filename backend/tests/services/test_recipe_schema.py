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


# --- regressions from the review of #38


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("зубчики", Unit.PIECE),
        ("зубчик", Unit.PIECE),
        ("пучок", Unit.PIECE),
        ("головка", Unit.PIECE),
        ("ст. ложки", Unit.TABLESPOON),
        ("столової ложки", Unit.TABLESPOON),
        ("чайної ложки", Unit.TEASPOON),
        ("ч. ложки", Unit.TEASPOON),
    ],
)
def test_units_named_in_the_prompt_are_accepted(written: str, expected: Unit) -> None:
    assert _ingredient(unit=written).unit is expected


@pytest.mark.parametrize(("written", "quantity", "ml"), [("чашка", 1, 250), ("стакани", 2, 500)])
def test_cups_are_converted_to_millilitres(written: str, quantity: float, ml: float) -> None:
    ingredient = _ingredient(unit=written, quantity=quantity)
    assert ingredient.unit is Unit.MILLILITER
    assert ingredient.quantity == ml


def test_step_starting_with_a_decimal_number_is_not_mangled() -> None:
    content = RecipeContent.model_validate(
        SAMPLE_RECIPE.model_dump() | {"steps": ["1.5 л води закип'ятити.", "2) Посолити."]}
    )
    assert content.steps == ["1.5 л води закип'ятити.", "Посолити."]


def test_numeric_string_quantity_is_coerced_not_dropped() -> None:
    ingredient = _ingredient(quantity="200", unit="г")
    assert ingredient.quantity == 200
    assert ingredient.unit is Unit.GRAM


def test_boolean_quantity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _ingredient(quantity=True, unit="г")


def test_overlong_step_fails_validation_instead_of_being_truncated() -> None:
    with pytest.raises(ValidationError):
        RecipeContent.model_validate(SAMPLE_RECIPE.model_dump() | {"steps": ["x" * 301]})


def test_read_model_accepts_a_legacy_row_shape() -> None:
    """Rows stored before the Unit enum: free-text units, long texts, no bounds."""
    from app.schemas.recipes import RecipeRead

    legacy = {
        "title": "Часникові грінки " * 6,  # > 80 chars
        "description": "Опис. " * 70,  # > 300 chars
        "cooking_time_minutes": 15,
        "servings": 2,
        "ingredients": [
            {"name": "Часник", "quantity": 2, "unit": "зубчики", "have_at_home": True},
            {"name": "Кріп", "quantity": 1, "unit": "пучок", "have_at_home": False},
        ],
        "steps": [f"Крок {i}" for i in range(25)],  # > 20 steps
        "tips": None,
        "clarifying_question": None,
    }
    read = RecipeRead.model_validate(
        legacy | {"id": 1, "products": ["часник"], "created_at": "2026-10-24T10:00:00Z"}
    )
    assert read.ingredients[0].unit == "зубчики"
    assert len(read.steps) == 25
