"""Recipe calories and macros (КБЖВ) from Silpo product cards.

Only Silpo data is counted: an ingredient without a matching product, without nutrition
attributes or with a quantity that cannot be converted to grams is reported but left out of
the totals. The response says how many ingredients were counted, so the UI can be honest.

The Silpo MCP client lives in `app.integrations.silpo`. `SilpoNutritionProvider` depends only on
the `SilpoSession` protocol (which `SilpoClient` satisfies) so it can be tested with a fake.
"""

import logging
import re
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import httpx
from fastapi import Depends
from mcp.shared.exceptions import McpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NutritionUnavailableError
from app.db.session import get_sessionmaker
from app.integrations.silpo import SilpoError, SilpoNotConnectedError, connect
from app.integrations.silpo.db_storage import DbTokenStorage
from app.schemas.nutrition import (
    GoalComparison,
    IngredientNutrition,
    IngredientStatus,
    NutritionFacts,
    RecipeNutrition,
)
from app.schemas.recipes import IngredientRead, RecipeRead
from app.services.recipes import get_recipe

logger = logging.getLogger(__name__)

# Attribute names exactly as the Silpo product card returns them.
ATTR_ENERGY = "Енергетична цінність (кКал/кДЖ)"
ATTR_PROTEIN = "Білки (г)"
ATTR_FAT = "Жири (г)"
ATTR_CARBS = "Вуглеводи (г)"

# Grams per unit. Millilitres are counted as grams (density ~1), good enough for КБЖВ.
UNIT_GRAMS = {
    "г": 1.0,
    "гр": 1.0,
    "кг": 1000.0,
    "мл": 1.0,
    "л": 1000.0,
    "ст. л.": 15.0,
    "ст.л.": 15.0,
    "ч. л.": 5.0,
    "ч.л.": 5.0,
}
PIECE_UNITS = {"шт", "шт."}

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_PACKAGE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(г|кг|мл|л)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProductNutrition:
    product_name: str
    # None when the product exists but its card has no calories / macros.
    per_100g: NutritionFacts | None
    # Weight of one sellable piece (bottle, pack), when the card states it in г/мл/кг/л.
    package_grams: float | None


class NutritionProvider(Protocol):
    """Looks up the matching product for ingredient names. Names with no product map to None.

    Implementations raise NutritionUnavailableError when the catalogue cannot be reached.
    """

    async def lookup(self, names: list[str]) -> dict[str, ProductNutrition | None]: ...


class SilpoSession(Protocol):
    """The subset of `SilpoClient` (mcp-silpo) this module needs.

    Values are raw MCP JSON, hence Any.
    """

    async def search_context(self) -> dict[str, Any]: ...

    async def find_products(self, names: list[str], limit: int = 3) -> dict[str, list[Any]]: ...

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]: ...


def _to_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and (m := _NUMBER.search(value)):
        return float(m.group().replace(",", "."))
    return None


def parse_attributes(attributes: dict[str, Any]) -> NutritionFacts | None:
    """Silpo card attributes -> facts per 100 g. None unless all four values are present.

    Energy comes as "kcal/kJ", e.g. "53/220"; the first number is kcal.
    """
    kcal = _to_float(attributes.get(ATTR_ENERGY))
    protein = _to_float(attributes.get(ATTR_PROTEIN))
    fat = _to_float(attributes.get(ATTR_FAT))
    carbs = _to_float(attributes.get(ATTR_CARBS))
    if kcal is None or protein is None or fat is None or carbs is None:
        return None
    return NutritionFacts(kcal=kcal, protein_g=protein, fat_g=fat, carbs_g=carbs)


def parse_package_grams(display_ratio: str | None, *, weighted: bool) -> float | None:
    """ "870г" -> 870, "1л" -> 1000; "10шт" -> None. Weighted goods show a price per 100 g,
    not a piece weight, so they never have one."""
    if weighted or not display_ratio:
        return None
    m = _PACKAGE.match(display_ratio)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "."))
    return amount * UNIT_GRAMS[m.group(2).lower()]


def ingredient_grams(ingredient: IngredientRead, package_grams: float | None) -> float | None:
    if ingredient.quantity is None:
        return None
    unit = ingredient.unit.strip().lower()
    if unit in UNIT_GRAMS:
        return ingredient.quantity * UNIT_GRAMS[unit]
    if unit in PIECE_UNITS and package_grams:
        return ingredient.quantity * package_grams
    return None


def _scale(facts: NutritionFacts, factor: float) -> NutritionFacts:
    return NutritionFacts(
        kcal=round(facts.kcal * factor, 1),
        protein_g=round(facts.protein_g * factor, 1),
        fat_g=round(facts.fat_g * factor, 1),
        carbs_g=round(facts.carbs_g * factor, 1),
    )


def _sum(items: list[NutritionFacts]) -> NutritionFacts:
    return NutritionFacts(
        kcal=round(sum(i.kcal for i in items), 1),
        protein_g=round(sum(i.protein_g for i in items), 1),
        fat_g=round(sum(i.fat_g for i in items), 1),
        carbs_g=round(sum(i.carbs_g for i in items), 1),
    )


def _ingredient_nutrition(
    ingredient: IngredientRead, found: ProductNutrition | None
) -> IngredientNutrition:
    def result(
        status: IngredientStatus, grams: float | None = None, total: NutritionFacts | None = None
    ) -> IngredientNutrition:
        return IngredientNutrition(
            name=ingredient.name,
            status=status,
            grams=grams,
            product_name=found.product_name if found else None,
            per_100g=found.per_100g if found else None,
            total=total,
        )

    if ingredient.quantity is None:
        return result("to_taste")
    if found is None:
        return result("no_product")
    if found.per_100g is None:
        return result("no_data")
    grams = ingredient_grams(ingredient, found.package_grams)
    if grams is None:
        return result("unknown_unit")
    return result("counted", round(grams, 1), _scale(found.per_100g, grams / 100))


def calculate(
    recipe_id: int,
    content: RecipeRead,
    products: dict[str, ProductNutrition | None],
    daily_kcal_goal: int | None,
) -> RecipeNutrition:
    """Pure part: combine the recipe with looked-up products (keyed by ingredient name)."""
    rows = [_ingredient_nutrition(i, products.get(i.name)) for i in content.ingredients]
    total = _sum([r.total for r in rows if r.total is not None])
    per_serving = _scale(total, 1 / content.servings)
    goal = (
        GoalComparison(
            daily_kcal=daily_kcal_goal,
            per_serving_percent=round(per_serving.kcal / daily_kcal_goal * 100, 1),
        )
        if daily_kcal_goal
        else None
    )
    return RecipeNutrition(
        recipe_id=recipe_id,
        servings=content.servings,
        total=total,
        per_serving=per_serving,
        counted_ingredients=sum(r.status == "counted" for r in rows),
        countable_ingredients=sum(r.status != "to_taste" for r in rows),
        ingredients=rows,
        goal=goal,
    )


async def recipe_nutrition(
    db: AsyncSession, provider: NutritionProvider, recipe_id: int, daily_kcal_goal: int | None
) -> RecipeNutrition:
    recipe = await get_recipe(db, recipe_id)
    content = RecipeRead.from_model(recipe)
    names = list(dict.fromkeys(i.name for i in content.ingredients if i.quantity is not None))
    products = await provider.lookup(names) if names else {}
    result = calculate(recipe_id, content, products, daily_kcal_goal)
    logger.info(
        "nutrition recipe_id=%s counted=%d/%d",
        recipe_id,
        result.counted_ingredients,
        result.countable_ingredients,
    )
    return result


class SilpoNutritionProvider:
    """Takes the first available Silpo product per ingredient and reads its card."""

    def __init__(self, silpo: SilpoSession) -> None:
        self._silpo = silpo

    async def lookup(self, names: list[str]) -> dict[str, ProductNutrition | None]:
        try:
            # One batch search for all names: Silpo serialises parallel searches.
            found = await self._silpo.find_products(names, limit=3)
            ctx = await self._silpo.search_context()
            result: dict[str, ProductNutrition | None] = {}
            for name in names:
                product = next((p for p in found.get(name, []) if p.get("available")), None)
                result[name] = await self._details(product, ctx) if product else None
            return result
        except (SilpoError, McpError, httpx.HTTPError, TimeoutError, OSError) as exc:
            logger.warning("silpo nutrition lookup failed: %s: %s", type(exc).__name__, exc)
            raise NutritionUnavailableError() from exc

    async def _details(self, product: dict[str, Any], ctx: dict[str, Any]) -> ProductNutrition:
        res = await self._silpo.call("silpo_get_product_details", {**ctx, "slug": product["slug"]})
        card = res.get("product") or {}
        return ProductNutrition(
            product_name=str(product["name"]),
            per_100g=parse_attributes(card.get("attributes") or {}),
            package_grams=parse_package_grams(
                product.get("displayRatio"), weighted=bool(product.get("weighted"))
            ),
        )


class ConnectedSilpoProvider:
    """Opens one MCP session per lookup. A localhost URL is the mock (no OAuth); the real server
    needs a logged-in token file, which only exists on a developer machine for now."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def lookup(self, names: list[str]) -> dict[str, ProductNutrition | None]:
        storage = DbTokenStorage(get_sessionmaker())
        try:
            async with connect(self._url, storage, interactive=False) as silpo:
                return await SilpoNutritionProvider(silpo).lookup(names)
        except SilpoNotConnectedError as exc:
            raise NutritionUnavailableError(
                "Сільпо не підключено: потрібен одноразовий вхід адміністратора"
            ) from exc
        except (SilpoError, McpError, httpx.HTTPError, TimeoutError, OSError) as exc:
            logger.warning("silpo connect failed: %s: %s", type(exc).__name__, exc)
            raise NutritionUnavailableError() from exc


def get_nutrition_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NutritionProvider:
    # Without SILPO_MCP_URL the endpoint answers 503 and the recipe itself keeps working.
    if not settings.silpo_mcp_url:
        raise NutritionUnavailableError(
            "Розрахунок КБЖВ не підключено до Сільпо (немає SILPO_MCP_URL)"
        )
    return ConnectedSilpoProvider(settings.silpo_mcp_url)


NutritionDep = Annotated[NutritionProvider, Depends(get_nutrition_provider)]
