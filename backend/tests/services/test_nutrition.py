from typing import Any

import pytest

from app.core.errors import NutritionUnavailableError
from app.schemas.nutrition import NutritionFacts
from app.schemas.recipes import IngredientRead
from app.services.nutrition import (
    ProductNutrition,
    SilpoNutritionProvider,
    calculate,
    ingredient_grams,
    parse_attributes,
    parse_package_grams,
)
from tests.conftest import SAMPLE_RECIPE

# Shape of `attributes` from a real silpo_get_product_details answer (mcp-silpo fixtures)
MILK_ATTRIBUTES = {
    "Країна": "Україна",
    "Енергетична цінність (кКал/кДЖ)": "53/220",
    "Білки (г)": 2.8,
    "Жири (г)": 2.5,
    "Вуглеводи (г)": 4.7,
}
MILK = NutritionFacts(kcal=53, protein_g=2.8, fat_g=2.5, carbs_g=4.7)


def test_parse_attributes_reads_kcal_and_macros() -> None:
    assert parse_attributes(MILK_ATTRIBUTES) == MILK


def test_parse_attributes_accepts_comma_decimals_in_strings() -> None:
    attrs = {**MILK_ATTRIBUTES, "Білки (г)": "2,8"}
    assert parse_attributes(attrs) == MILK


def test_parse_attributes_without_full_data_returns_none() -> None:
    assert parse_attributes({"Країна": "Україна"}) is None
    assert parse_attributes({k: v for k, v in MILK_ATTRIBUTES.items() if k != "Жири (г)"}) is None


@pytest.mark.parametrize(
    ("ratio", "weighted", "expected"),
    [("870г", False, 870), ("1,5л", False, 1500), ("1кг", False, 1000), ("10шт", False, None)],
)
def test_parse_package_grams(ratio: str, weighted: bool, expected: float | None) -> None:
    assert parse_package_grams(ratio, weighted=weighted) == expected


def test_weighted_product_has_no_package_weight() -> None:
    # weighted goods show "100г" as the price unit, not as a piece weight
    assert parse_package_grams("100г", weighted=True) is None


@pytest.mark.parametrize(
    ("quantity", "unit", "package", "expected"),
    [
        (200, "г", None, 200),
        (0.5, "кг", None, 500),
        (250, "мл", None, 250),
        (2, "ст. л.", None, 30),
        (1, "ч. л.", None, 5),
        (2, "шт", 150, 300),
        (2, "шт", None, None),
        (None, "за смаком", None, None),
        (1, "пучок", None, None),
    ],
)
def test_ingredient_grams(
    quantity: float | None, unit: str, package: float | None, expected: float | None
) -> None:
    ingredient = IngredientRead(name="x", quantity=quantity, unit=unit, have_at_home=True)
    assert ingredient_grams(ingredient, package) == expected


def test_calculate_counts_only_ingredients_with_silpo_data() -> None:
    tomato = ProductNutrition(
        product_name="Помідор",
        per_100g=NutritionFacts(kcal=20, protein_g=1, fat_g=0.2, carbs_g=4),
        package_grams=150,
    )
    # SAMPLE_RECIPE: 4 eggs (not found), 1 tomato, salt to taste; 2 servings
    result = calculate(1, SAMPLE_RECIPE, {"Яйця": None, "Помідор": tomato}, daily_kcal_goal=2000)

    statuses = {i.name: i.status for i in result.ingredients}
    assert statuses == {"Яйця": "no_product", "Помідор": "counted", "Сіль": "to_taste"}
    assert result.counted_ingredients == 1
    assert result.countable_ingredients == 2
    assert result.total == NutritionFacts(kcal=30, protein_g=1.5, fat_g=0.3, carbs_g=6)
    assert result.per_serving.kcal == 15
    assert result.per_serving.carbs_g == 3
    assert result.goal is not None
    assert result.goal.per_serving_percent == 0.8


def test_calculate_marks_product_without_card_data_as_no_data() -> None:
    eggs = ProductNutrition(product_name="Яйця курячі С0", per_100g=None, package_grams=None)
    result = calculate(1, SAMPLE_RECIPE, {"Яйця": eggs, "Помідор": None}, daily_kcal_goal=None)

    rows = {i.name: i for i in result.ingredients}
    assert rows["Яйця"].status == "no_data"
    assert rows["Яйця"].product_name == "Яйця курячі С0"
    assert rows["Помідор"].status == "no_product"


def test_calculate_without_goal_and_data_returns_zeros() -> None:
    result = calculate(1, SAMPLE_RECIPE, {}, daily_kcal_goal=None)
    assert result.goal is None
    assert result.total.kcal == 0
    assert result.counted_ingredients == 0


class FakeSilpo:
    """Mimics SilpoClient from mcp-silpo with the mock server's answer shapes."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.detail_calls: list[str] = []

    async def search_context(self) -> dict[str, Any]:
        return {"branchId": "b", "deliveryType": "DeliveryHome"}

    async def find_products(self, names: list[str], limit: int = 3) -> dict[str, list[Any]]:
        if self.fail:
            raise RuntimeError("silpo down")
        catalogue = {
            "Молоко": [
                {"name": "Молоко (немає)", "slug": "gone", "available": False},
                {
                    "name": "Молоко Галичина 2,5%",
                    "slug": "milk",
                    "available": True,
                    "weighted": False,
                    "displayRatio": "950г",
                },
            ],
            "Сир": [{"name": "Сир", "slug": "cheese", "available": True, "weighted": True}],
        }
        return {n: catalogue.get(n, []) for n in names}

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        assert name == "silpo_get_product_details"
        assert args is not None and args["branchId"] == "b"
        self.detail_calls.append(args["slug"])
        attributes = MILK_ATTRIBUTES if args["slug"] == "milk" else {}
        return {"success": True, "product": {"attributes": attributes}}


async def test_silpo_provider_reads_first_available_product_card() -> None:
    silpo = FakeSilpo()
    result = await SilpoNutritionProvider(silpo).lookup(["Молоко", "Сир", "Кіноа"])

    assert result["Молоко"] == ProductNutrition(
        product_name="Молоко Галичина 2,5%", per_100g=MILK, package_grams=950
    )
    # card without nutrition attributes: the product is kept, the data is not
    assert result["Сир"] == ProductNutrition(product_name="Сир", per_100g=None, package_grams=None)
    assert result["Кіноа"] is None  # nothing found
    assert silpo.detail_calls == ["milk", "cheese"]


async def test_silpo_provider_failure_raises_unavailable() -> None:
    with pytest.raises(NutritionUnavailableError):
        await SilpoNutritionProvider(FakeSilpo(fail=True)).lookup(["Молоко"])
