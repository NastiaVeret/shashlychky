"""The shopping list over a fake Silpo: what to buy, and what to do when it is out or short."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.core.errors import ProductDataUnavailableError
from app.integrations.silpo.catalog import ProductCatalog
from app.schemas.recipes import Ingredient, RecipeContent, Unit
from app.services.shopping import build_shopping_list, shopping_lines

CTX = {"branchId": "b", "deliveryType": "DeliveryHome"}


def hit(slug: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"id-{slug}",
        "name": slug.title(),
        "slug": slug,
        "available": True,
        "price": 100.0,
        "stock": 50,
        "weighted": False,
        "step": 1,
        "displayRatio": "300г",
        **fields,
    }


class FakeSilpo:
    def __init__(
        self,
        catalogue: dict[str, list[dict[str, Any]]],
        *,
        similar: list[dict[str, Any]] | None = None,
        attributes: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.catalogue = catalogue
        self.similar = similar or []
        self.attributes = attributes or {}
        self.search_calls = 0

    async def search_context(self) -> dict[str, Any]:
        return CTX

    async def find_products(
        self, names: list[str], limit: int = 3, ctx: dict[str, Any] | None = None
    ) -> dict[str, list[Any]]:
        self.search_calls += 1
        return {n: self.catalogue.get(n, [])[:limit] for n in names}

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        assert args is not None
        if name == "silpo_get_similar_products":
            return {"products": self.similar}
        slug = args["slug"]
        return {
            "product": {
                "url": f"https://silpo.ua/{slug}",
                "attributes": self.attributes.get(slug, {}),
            }
        }


class SessionProvider:
    def __init__(self, silpo: FakeSilpo | None, *, down: bool = False) -> None:
        self.silpo, self.down, self.runs = silpo, down, 0

    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        self.runs += 1
        if self.down or self.silpo is None:
            raise ProductDataUnavailableError()
        return await work(ProductCatalog(self.silpo))  # type: ignore[arg-type]


def recipe(*ingredients: Ingredient) -> RecipeContent:
    return RecipeContent(
        title="Страва",
        description="Опис.",
        cooking_time_minutes=10,
        servings=2,
        ingredients=list(ingredients),
        steps=["Змішати."],
    )


def need(name: str, quantity: float | None, unit: Unit = Unit.GRAM) -> Ingredient:
    return Ingredient(name=name, quantity=quantity, unit=unit, have_at_home=False)


async def lines_for(
    silpo: FakeSilpo | None, *ingredients: Ingredient, allergies: list[str] | None = None
) -> dict[str, Any]:
    provider = SessionProvider(silpo)
    lines = await shopping_lines(provider, recipe(*ingredients), allergies or [])  # type: ignore[arg-type]
    return {line.name: line for line in lines}


async def test_everything_at_home_never_asks_silpo() -> None:
    provider = SessionProvider(None)
    home = Ingredient(name="Рис", quantity=200, unit=Unit.GRAM, have_at_home=True)
    lines = await shopping_lines(provider, recipe(home), [])  # type: ignore[arg-type]
    assert [line.status for line in lines] == ["at_home"] and provider.runs == 0


async def test_to_taste_is_not_looked_up() -> None:
    provider = SessionProvider(None)
    salt = need("Сіль", None, Unit.TO_TASTE)
    lines = await shopping_lines(provider, recipe(salt), [])  # type: ignore[arg-type]
    assert lines[0].status == "to_taste" and provider.runs == 0


async def test_ok_line_has_product_pack_text_and_price() -> None:
    eggs = hit("eggs", price=138.03, displayRatio="10шт")
    silpo = FakeSilpo({"Яйця": [eggs]})
    line = (await lines_for(silpo, need("Яйця", 3, Unit.PIECE)))["Яйця"]

    assert line.status == "ok"
    assert line.product is not None and line.product.package == "10шт"  # Silpo's own wording
    assert line.product.url == "https://silpo.ua/eggs"
    assert line.purchase is not None and line.purchase.quantity == 1
    assert line.purchase.total_price == 138.03 and line.purchase.leftover_pieces == 7


async def test_one_batch_search_serves_the_whole_recipe() -> None:
    silpo = FakeSilpo({"Яйця": [hit("eggs", displayRatio="10шт")], "Сир": [hit("cheese")]})
    await lines_for(silpo, need("Яйця", 3, Unit.PIECE), need("Сир", 100))
    assert silpo.search_calls == 1


async def test_unknown_ingredient_is_no_product() -> None:
    line = (await lines_for(FakeSilpo({}), need("Кіноа", 100)))["Кіноа"]
    assert line.status == "no_product" and line.product is None and line.alternatives == []


async def test_unreadable_package_is_shown_as_silpo_prints_it() -> None:
    silpo = FakeSilpo({"Йогурт": [hit("yogurt", displayRatio="2х150г")]})
    line = (await lines_for(silpo, need("Йогурт", 200)))["Йогурт"]
    assert line.status == "unknown_package" and line.purchase is None
    assert line.product is not None and line.product.package == "2х150г"


async def test_an_empty_pack_is_shown_as_silpo_prints_it() -> None:
    silpo = FakeSilpo({"Сир": [hit("cheese", displayRatio="0г")]})
    line = (await lines_for(silpo, need("Сир", 200)))["Сир"]
    assert line.status == "unknown_package" and line.purchase is None


async def test_weighted_product_is_bought_in_kg_by_the_step() -> None:
    sausage = hit("sausage", weighted=True, step=0.65, price=364, displayRatio="100г")
    line = (await lines_for(FakeSilpo({"Ковбаса": [sausage]}), need("Ковбаса", 200)))["Ковбаса"]
    assert line.status == "ok" and line.purchase is not None
    assert (line.purchase.quantity, line.purchase.quantity_unit) == (0.65, "kg")


async def test_short_stock_offers_alternatives_with_enough_stock_first() -> None:
    hits = [
        hit("short", stock=2),  # the pick: needs 3 packs, 2 left
        hit("alt-small", stock=1),
        hit("alt-big", stock=40),
        hit("alt-gone", available=False),
    ]
    line = (await lines_for(FakeSilpo({"Борошно": hits}), need("Борошно", 900)))["Борошно"]

    assert line.status == "partial_stock"
    assert line.purchase is not None and line.purchase.quantity == 3
    assert [a.name for a in line.alternatives] == ["Alt-Big", "Alt-Small"]
    assert [a.enough_stock for a in line.alternatives] == [True, False]


async def test_nothing_available_falls_back_to_silpo_similar_products() -> None:
    silpo = FakeSilpo(
        {"Молоко": [hit("gone", available=False)]},
        similar=[hit("close"), hit("closer", available=False)],
    )
    line = (await lines_for(silpo, need("Молоко", 250)))["Молоко"]

    assert line.status == "out_of_stock"
    assert line.product is not None and line.product.name == "Gone"
    assert [a.name for a in line.alternatives] == ["Close"]  # an unavailable one is no alternative


async def test_alternatives_are_vetted_against_the_users_allergies() -> None:
    silpo = FakeSilpo(
        {"Напій": [hit("gone", available=False)]},
        similar=[hit("milk-free"), hit("dairy")],
        attributes={"dairy": {"Містить алергени": "МОЛОКО"}},
    )
    line = (await lines_for(silpo, need("Напій", 250), allergies=["молоко"]))["Напій"]

    by_name = {a.name: a for a in line.alternatives}
    assert by_name["Dairy"].allergen_source == "declared"
    assert [(x.allergy, x.level) for x in by_name["Dairy"].alerts] == [("молоко", "contains")]
    assert by_name["Milk-Free"].alerts == [] and by_name["Milk-Free"].allergen_source == "unknown"


async def test_silpo_down_is_a_503_not_a_half_empty_list() -> None:
    with pytest.raises(ProductDataUnavailableError):
        await shopping_lines(
            SessionProvider(None, down=True), recipe(need("Яйця", 3, Unit.PIECE)), []
        )  # type: ignore[arg-type]


async def test_totals_count_only_lines_that_can_be_bought() -> None:
    silpo = FakeSilpo(
        {
            "Яйця": [hit("eggs", price=138.03, displayRatio="10шт")],
            "Борошно": [hit("flour", stock=1, price=50)],  # short: needs 3, has 1
            "Йогурт": [hit("yogurt", displayRatio="2х150г")],
        }
    )
    lines = await shopping_lines(
        SessionProvider(silpo),  # type: ignore[arg-type]
        recipe(
            need("Яйця", 3, Unit.PIECE), need("Борошно", 900), need("Йогурт", 200), need("Кіноа", 1)
        ),
        [],
    )
    result = build_shopping_list(1, lines)

    assert [line.status for line in result.lines] == [
        "ok",
        "partial_stock",
        "unknown_package",
        "no_product",
    ]
    assert result.total_price == 138.03
    assert result.needs_attention == 3
