"""Manual check of the shopping list and the allergen check against the REAL Silpo server.

Read-only: it searches, reads product cards and asks for similar products. It never touches the
cart. One huge quantity is included on purpose, to force the "short on stock" path and see real
alternatives. Needs a login first (`python -m scripts.silpo_login`).

    SILPO_MCP_URL=https://mcp.silpo.ua/mcp uv run python -m scripts.silpo_check_product_checks
    ... --allergy яйця --allergy молоко      # also check against these allergies
"""

import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable

from app.integrations.silpo import connect
from app.integrations.silpo.catalog import ProductCatalog
from app.schemas.recipes import Ingredient, RecipeContent, Unit
from app.services.product_allergens import check_ingredient
from app.services.shopping import shopping_lines

URL = os.environ.get("SILPO_MCP_URL", "https://mcp.silpo.ua/mcp")

RECIPE = RecipeContent(
    title="Перевірка",
    description="Не справжній рецепт.",
    cooking_time_minutes=1,
    servings=1,
    ingredients=[
        Ingredient(name="Яйця", quantity=3, unit=Unit.PIECE, have_at_home=False),
        Ingredient(name="Молоко", quantity=250, unit=Unit.MILLILITER, have_at_home=False),
        Ingredient(name="Майонез", quantity=100, unit=Unit.GRAM, have_at_home=False),
        Ingredient(name="Ковбаса варена", quantity=200, unit=Unit.GRAM, have_at_home=False),
        Ingredient(name="Шоколад молочний", quantity=50, unit=Unit.GRAM, have_at_home=False),
        Ingredient(name="Борошно", quantity=100000, unit=Unit.GRAM, have_at_home=False),  # too much
        Ingredient(name="Помідор", quantity=2, unit=Unit.PIECE, have_at_home=False),  # piece weight
        Ingredient(
            name="Картопля", quantity=4, unit=Unit.PIECE, have_at_home=False
        ),  # bag vs piece
        Ingredient(name="Олія", quantity=100, unit=Unit.MILLILITER, have_at_home=False),  # density
        Ingredient(name="Кіноаксвзщ", quantity=100, unit=Unit.GRAM, have_at_home=False),  # no hit
        Ingredient(name="Сіль", quantity=None, unit=Unit.TO_TASTE, have_at_home=False),
    ],
    steps=["Нічого не робити."],
)


class Counted:
    """Wraps the client and counts the Silpo calls a lookup takes."""

    def __init__(self, silpo: object) -> None:
        self.silpo = silpo
        self.calls = 0

    async def search_context(self):  # type: ignore[no-untyped-def]
        return await self.silpo.search_context()  # type: ignore[attr-defined]

    async def find_products(self, names, limit=3, ctx=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        return await self.silpo.find_products(names, limit=limit, ctx=ctx)  # type: ignore[attr-defined]

    async def call(self, name, args=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        return await self.silpo.call(name, args)  # type: ignore[attr-defined]


class OneSession:
    def __init__(self, silpo: Counted) -> None:
        self.silpo = silpo

    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        return await work(ProductCatalog(self.silpo))  # type: ignore[arg-type]


async def main() -> None:
    allergies = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--allergy"]
    async with connect(URL) as silpo:
        counted = Counted(silpo)
        started = time.monotonic()
        lines = await shopping_lines(OneSession(counted), RECIPE, allergies)  # type: ignore[arg-type]
        took = time.monotonic() - started

        print(f"=== список покупок ({took:.1f} с, {counted.calls} викликів) ===")
        for line in lines:
            product = line.product
            print(f"\n{line.name}: {line.status}")
            if line.needed_g is not None and line.grams_basis != "exact":
                print(
                    f"  потрібно {line.quantity} {line.unit} ≈ {line.needed_g} г"
                    f" ({line.grams_basis}, {line.grams_per_unit} г на одиницю)"
                )
            if product:
                print(
                    f"  товар: {product.name} | пакування: {product.package} | ціна {product.price}"
                    f" | залишок {product.stock} | вагові: {product.weighted}, крок {product.step}"
                )
            if line.purchase:
                print(
                    f"  купити{' (оцінка)' if line.purchase.estimated else ''}:"
                    f" {line.purchase.quantity} {line.purchase.quantity_unit}"
                    f" = {line.purchase.total_price} грн, лишиться: {line.purchase.leftover_g} г"
                    f" / {line.purchase.leftover_pieces} шт"
                )
            for alt in line.alternatives:
                print(
                    f"  заміна: {alt.name} | {alt.package} | вистачає: {alt.enough_stock}"
                    f" | алергени: {alt.allergen_source} {[a.allergy for a in alt.alerts]}"
                )

        print("\n=== алергени ===")
        catalog = ProductCatalog(counted)  # type: ignore[arg-type]
        names = [i.name for i in RECIPE.ingredients if i.quantity is not None]
        matches = await catalog.match(names)
        for name in names:
            row = check_ingredient(name, matches.get(name), allergies)
            print(
                f"{name}: {row.source} | містить {row.contains} | сліди {row.traces}"
                f" | імовірно {row.likely} | ваші збіги {[a.allergy for a in row.alerts]}"
            )


asyncio.run(main())
