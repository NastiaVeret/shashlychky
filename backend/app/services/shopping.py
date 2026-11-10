"""The shopping list of a recipe: what to buy at Silpo, how much, and what to do when it is short.

Built on the same product lookup as КБЖВ and the allergen check (`ProductCatalog`), so one
request costs one search plus a few cards. Only ingredients the user does not have at home are
looked up. When the pick is out of stock or short, the list carries a few alternatives, each
already vetted against the user's allergies. Choosing the best alternative is deliberately left
open: the order is only "enough stock first, then Silpo's own order".
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.silpo.catalog import Candidate, IngredientMatch, ProductCatalog
from app.models.user import User
from app.schemas.recipes import IngredientRead, RecipeRead
from app.schemas.shopping import Alternative, ProductOption, RecipeShoppingList, ShoppingLine
from app.services.catalog import CatalogProvider
from app.services.packaging import has_enough_stock, plan_purchase
from app.services.product_allergens import check_ingredient, product_check_allergies
from app.services.profiles import get_profile
from app.services.recipes import get_recipe
from app.services.units import to_grams

MAX_ALTERNATIVES = 3
_PROBLEMS = {"no_product", "out_of_stock", "partial_stock", "unknown_package"}


def _option(candidate: Candidate, url: str | None) -> ProductOption:
    return ProductOption(
        product_id=candidate.product_id,
        name=candidate.name,
        url=url,
        price=candidate.price,
        stock=candidate.stock,
        weighted=candidate.weighted,
        step=candidate.step,
        package=candidate.display_ratio,
    )


def _line(ingredient: IngredientRead, status: str, **fields: object) -> ShoppingLine:
    grams = (
        to_grams(ingredient.name, ingredient.quantity, ingredient.unit)
        if ingredient.quantity is not None
        else None
    )
    return ShoppingLine.model_validate(
        {
            "name": ingredient.name,
            "status": status,
            "have_at_home": ingredient.have_at_home,
            "quantity": ingredient.quantity,
            "unit": ingredient.unit,
            "needed_g": round(grams.value, 1) if grams else None,
            "grams_basis": grams.basis if grams else None,
            "grams_per_unit": grams.per_unit if grams else None,
            "product": None,
            "purchase": None,
            "alternatives": [],
            **fields,
        }
    )


def _static_line(ingredient: IngredientRead) -> ShoppingLine | None:
    """Ingredients that need no Silpo lookup at all."""
    if ingredient.have_at_home:
        return _line(ingredient, "at_home")
    if ingredient.quantity is None:
        return _line(ingredient, "to_taste")
    return None


async def _alternatives(
    catalog: ProductCatalog,
    ingredient: IngredientRead,
    pick: Candidate,
    search_hits: Sequence[Candidate],
    allergies: Sequence[str],
) -> list[Alternative]:
    pool = [c for c in search_hits if c.slug != pick.slug and c.available]
    if len(pool) < MAX_ALTERNATIVES:
        seen = {pick.slug, *(c.slug for c in pool)}
        pool += [c for c in await catalog.similar(pick) if c.available and c.slug not in seen]
    pool = pool[:MAX_ALTERNATIVES]
    cards = await catalog.cards(pool)

    options: list[Alternative] = []
    for candidate in pool:
        card = cards[candidate.slug]
        purchase = plan_purchase(ingredient, candidate)
        verdict = check_ingredient(
            ingredient.name, IngredientMatch(ingredient.name, [candidate], card), allergies
        )
        options.append(
            Alternative(
                **_option(candidate, card.url).model_dump(),
                enough_stock=purchase is not None and has_enough_stock(purchase, candidate),
                purchase=purchase,
                allergen_source=verdict.source,
                alerts=verdict.alerts,
            )
        )
    return sorted(options, key=lambda a: not a.enough_stock)  # stable: Silpo's order otherwise


async def _lookup_line(
    catalog: ProductCatalog,
    ingredient: IngredientRead,
    match: IngredientMatch | None,
    allergies: Sequence[str],
) -> ShoppingLine:
    if match is None or not match.candidates:
        return _line(ingredient, "no_product")
    card = match.card
    if card is None:  # Silpo knows products for it, but none is available here and now
        first = match.candidates[0]
        alternatives = await _alternatives(catalog, ingredient, first, [], allergies)
        return _line(
            ingredient, "out_of_stock", product=_option(first, None), alternatives=alternatives
        )

    pick = card.candidate
    product = _option(pick, card.url)
    purchase = plan_purchase(ingredient, pick)
    if purchase is None:  # shown with Silpo's own package wording, nothing is guessed
        return _line(ingredient, "unknown_package", product=product)
    if has_enough_stock(purchase, pick):
        return _line(ingredient, "ok", product=product, purchase=purchase)
    alternatives = await _alternatives(catalog, ingredient, pick, match.candidates, allergies)
    return _line(
        ingredient, "partial_stock", product=product, purchase=purchase, alternatives=alternatives
    )


def build_shopping_list(recipe_id: int, lines: list[ShoppingLine]) -> RecipeShoppingList:
    totals = [
        line.purchase.total_price
        for line in lines
        if line.status == "ok" and line.purchase and line.purchase.total_price is not None
    ]
    return RecipeShoppingList(
        recipe_id=recipe_id,
        lines=lines,
        total_price=round(sum(totals), 2) if totals else None,
        needs_attention=sum(line.status in _PROBLEMS for line in lines),
    )


async def shopping_lines(
    provider: CatalogProvider, content: RecipeRead, allergies: Sequence[str]
) -> list[ShoppingLine]:
    """One line per ingredient, in recipe order. Silpo is asked only for what is not at home."""
    static = [_static_line(i) for i in content.ingredients]
    to_look_up = [(n, i) for n, i in enumerate(content.ingredients) if static[n] is None]

    looked_up: dict[int, ShoppingLine] = {}
    if to_look_up:
        names = list(dict.fromkeys(i.name for _, i in to_look_up))

        async def work(catalog: ProductCatalog) -> dict[int, ShoppingLine]:
            matches = await catalog.match(names)
            return {
                n: await _lookup_line(catalog, i, matches.get(i.name), allergies)
                for n, i in to_look_up
            }

        looked_up = await provider.run(work)
    return [s or looked_up[n] for n, s in enumerate(static)]


async def recipe_shopping_list(
    db: AsyncSession, provider: CatalogProvider, recipe_id: int, user: User | None
) -> RecipeShoppingList:
    """Raises ProductDataUnavailableError (503) when Silpo cannot be asked: without it there is
    nothing honest to put on the list."""
    content = RecipeRead.from_model(await get_recipe(db, recipe_id))
    allergies = product_check_allergies(get_profile(user)) if user else []
    return build_shopping_list(recipe_id, await shopping_lines(provider, content, allergies))
