"""Allergens of the products behind a recipe's ingredients.

`app.services.allergens` guards the recipe *text*; it cannot see an allergen that hides inside a
product ("майонез" contains eggs, though the word never appears). This module looks at the
products instead, from two sources:

1. Silpo's product card, when it has the "Містить алергени" attribute. Silpo fills it for only some
   products, so its absence proves nothing.
2. A short dictionary of what a type of product usually contains. It is a hint ("likely"), never a
   guarantee, and is only used when the card says nothing.

Without either, the ingredient is "unknown": the caller shows the product page link and the user
checks the label. Nothing here ever reports a product as safe.
"""

import re
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProductDataUnavailableError
from app.integrations.silpo.catalog import IngredientMatch
from app.models.user import User
from app.schemas.allergens import (
    AlertLevel,
    AllergenAlert,
    IngredientAllergens,
    RecipeAllergenCheck,
)
from app.schemas.recipes import RecipeRead
from app.services.allergens import find_allergens
from app.services.catalog import CatalogProvider
from app.services.profiles import get_profile
from app.services.recipes import get_recipe

# Attribute name exactly as the Silpo product card returns it, e.g.
# "ЯЙЦЯ.  Може містити сліди: ГІРЧИЦЮ, СЕЛЕРУ, СОЮ, МОЛОКО."
ATTR_ALLERGENS = "Містить алергени"

_TRACES_MARK = re.compile(r"може\s+містити(?:\s+сліди)?\s*:?", re.IGNORECASE)
_LEADING_LABEL = re.compile(r"^\s*(?:містить|алергени)\s*:?\s*", re.IGNORECASE)
_SEPARATORS = re.compile(r"[,;.]")

# Product type -> allergens it usually contains. Every word of the type must appear in the
# ingredient or product name (same stem rules as the recipe check). Kept short and uncontroversial
# on purpose: extend it with the team, and move to a real data source when there is one.
TYPICAL_ALLERGENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("майонез", ("яйця", "гірчиця")),
    ("соєвий соус", ("соя", "пшениця")),
    ("шоколад молочний", ("молоко",)),
    ("вершки", ("молоко",)),
    ("сметана", ("молоко",)),
    ("йогурт", ("молоко",)),
    ("кефір", ("молоко",)),
    ("масло вершкове", ("молоко",)),
    ("сир", ("молоко",)),
    ("морозиво", ("молоко",)),
    ("борошно пшеничне", ("глютен", "пшениця")),
    ("хліб", ("глютен", "пшениця")),
    ("батон", ("глютен", "пшениця")),
    ("макарони", ("глютен", "пшениця")),
    ("спагеті", ("глютен", "пшениця")),
    ("локшина", ("глютен", "пшениця")),
    ("пельмені", ("глютен", "пшениця", "яйця")),
    ("вареники", ("глютен", "пшениця")),
)


def _items(text: str) -> list[str]:
    parts = (p.strip(" .;\t\n") for p in _SEPARATORS.split(text))
    return [p for p in parts if p]


def parse_allergen_attribute(value: object) -> tuple[list[str], list[str]] | None:
    """The card attribute as (contains, traces), lower-cased. None when there is no usable text."""
    if not isinstance(value, str) or not value.strip():
        return None
    head, *rest = _TRACES_MARK.split(value.casefold(), maxsplit=1)
    return _items(_LEADING_LABEL.sub("", head)), _items(rest[0] if rest else "")


def likely_allergens(*names: str) -> list[str]:
    """Allergens that products of this type usually contain, judging by the given names."""
    found: list[str] = []
    for product_type, allergens in TYPICAL_ALLERGENS:
        if find_allergens([product_type], names):
            found.extend(a for a in allergens if a not in found)
    return found


def _alerts(
    allergies: Sequence[str],
    names: list[str],
    contains: list[str],
    traces: list[str],
    likely: list[str],
) -> list[AllergenAlert]:
    """Allergies of the user found in each list, most serious level first, each reported once.

    The ingredient's and the product's own names count as "contains": a card that lists no
    allergens must not hide that the product is called "Молоко" or "Яйця курячі"."""
    levels: tuple[tuple[AlertLevel, list[str]], ...] = (
        ("contains", names),
        ("contains", contains),
        ("traces", traces),
        ("likely", likely),
    )
    alerts: list[AllergenAlert] = []
    seen: set[str] = set()
    for level, items in levels:
        for allergy in find_allergens(allergies, items):
            if allergy not in seen:
                seen.add(allergy)
                alerts.append(AllergenAlert(allergy=allergy, level=level))
    return alerts


def check_ingredient(
    name: str,
    match: IngredientMatch | None,
    allergies: Sequence[str],
) -> IngredientAllergens:
    card = match.card if match else None
    product_name = card.candidate.name if card else None
    parsed = parse_allergen_attribute(card.attributes.get(ATTR_ALLERGENS)) if card else None

    contains: list[str] = []
    traces: list[str] = []
    likely: list[str] = []
    alert_likely: list[str] = []
    if parsed is not None and (parsed[0] or parsed[1]):
        source = "declared"
        contains, traces = parsed
    else:  # no card, no attribute, or an attribute with nothing readable in it
        likely = likely_allergens(name, *([product_name] if product_name else []))
        source = "likely" if likely else "unknown"
        alert_likely = likely
    return IngredientAllergens(
        name=name,
        source=source,
        product_name=product_name,
        product_url=card.url if card else None,
        contains=contains,
        traces=traces,
        likely=likely,
        alerts=_alerts(
            allergies,
            [name, *([product_name] if product_name else [])],
            contains,
            traces,
            alert_likely,
        ),
    )


def build_allergen_check(
    recipe_id: int,
    content: RecipeRead,
    matches: dict[str, IngredientMatch],
    allergies: Sequence[str] | None,
    *,
    silpo_checked: bool,
) -> RecipeAllergenCheck:
    names = list(dict.fromkeys(i.name for i in content.ingredients))
    rows = [check_ingredient(n, matches.get(n), allergies or []) for n in names]
    return RecipeAllergenCheck(
        recipe_id=recipe_id,
        profile_applied=allergies is not None,
        silpo_checked=silpo_checked,
        ingredients=rows,
        unknown_ingredients=sum(r.source == "unknown" for r in rows),
        has_alerts=any(r.alerts for r in rows),
    )


async def recipe_allergen_check(
    db: AsyncSession,
    provider: CatalogProvider,
    recipe_id: int,
    user: User | None,
) -> RecipeAllergenCheck:
    """Allergen check of a stored recipe. If Silpo is unreachable the dictionary hints are still
    returned (`silpo_checked=False`): a degraded answer is better than none for allergens."""
    content = RecipeRead.from_model(await get_recipe(db, recipe_id))
    names = list(dict.fromkeys(i.name for i in content.ingredients))
    matches: dict[str, IngredientMatch] = {}
    silpo_checked = False
    try:
        if names:
            matches = await provider.run(lambda catalog: catalog.match(names))
        silpo_checked = True
    except ProductDataUnavailableError:
        pass
    allergies = get_profile(user).allergies if user else None
    return build_allergen_check(recipe_id, content, matches, allergies, silpo_checked=silpo_checked)
