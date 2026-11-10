"""Checks applied to a generated recipe.

Structural correctness is already guaranteed by `RecipeContent`: if we got an object at all, the
units are from the enum and the bounds hold. What is left - and what R2 is actually about - is
*semantic* drift: ingredients the user never mentioned, a diet or allergy ignored, an instruction
smuggled in through a product name, a question that should have been asked.

Word matching reuses `find_allergens`, the project's stem matcher, so "сир" does not match
"сирий" and "молоко" does match "молочний".
"""

from dataclasses import dataclass

from app.schemas.profiles import UserProfile
from app.schemas.recipes import RecipeContent, Unit, is_unit_word
from app.services.allergens import find_allergens, recipe_texts
from evals.cases import EvalCase

# What the system prompt allows the model to add without the user listing it.
BASIC_PANTRY = (
    "сіль",
    "перець",
    "цукор",
    "олія",
    "вершкове масло",
    "вода",
    "борошно",
    "спеції",
    "приправи",
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


# Words a user writes next to an amount; they are not part of the product's name.
_QUANTITY_WORDS = frozenset({"пів", "половина", "трохи", "кілька", "декілька", "шматок"})


def _mentions(term: str, texts: list[str]) -> bool:
    return bool(find_allergens([term], texts))


def product_term(product: str) -> str:
    """The product without the amount the user typed into it: "2 кг картоплі" -> "картоплі".

    The model is expected to strip these, so matching the raw string would fail every time the
    user writes a quantity - a false alarm about the model, caused by the check.
    """
    words = [
        word
        for word in product.split()
        if not word.replace(",", "").replace(".", "").isdigit()
        and not is_unit_word(word)
        and word.casefold() not in _QUANTITY_WORDS
    ]
    return " ".join(words) or product


def _is_expected(name: str, known: list[str]) -> bool:
    """Is this ingredient something the user has, or a basic the prompt allows?"""
    return any(_mentions(term, [name]) for term in known)


def _known_terms(case: EvalCase) -> list[str]:
    profile = case.profile or UserProfile()
    products = [product_term(p) for p in case.request.products]
    return [*products, *profile.pantry, *BASIC_PANTRY]


def check_servings(case: EvalCase, content: RecipeContent) -> CheckResult:
    asked = case.request.servings
    return CheckResult(
        "servings_respected",
        content.servings == asked,
        f"asked {asked}, got {content.servings}",
    )


def check_uses_user_products(case: EvalCase, content: RecipeContent) -> CheckResult:
    names = [i.name for i in content.ingredients]
    used = [p for p in case.request.products if any(_mentions(product_term(p), [n]) for n in names)]
    # A clarifying question means the model could not use the input, which is a valid answer.
    passed = bool(used) or content.clarifying_question is not None
    return CheckResult(
        "uses_user_products", passed, f"used {len(used)}/{len(case.request.products)}"
    )


def check_foreign_ingredients(case: EvalCase, content: RecipeContent) -> CheckResult:
    known = _known_terms(case)
    foreign = [i.name for i in content.ingredients if not _is_expected(i.name, known)]
    passed = len(foreign) <= case.max_foreign_ingredients
    return CheckResult(
        "foreign_ingredients_within_limit",
        passed,
        f"{len(foreign)} beyond the allowance: {', '.join(foreign) or '-'}",
    )


def check_have_at_home_honest(case: EvalCase, content: RecipeContent) -> CheckResult:
    """An ingredient flagged "вдома" must be one the user actually has, or a basic."""
    known = _known_terms(case)
    lying = [
        i.name for i in content.ingredients if i.have_at_home and not _is_expected(i.name, known)
    ]
    return CheckResult(
        "have_at_home_honest", not lying, f"claimed at home: {', '.join(lying) or '-'}"
    )


def check_forbidden_terms(case: EvalCase, content: RecipeContent) -> CheckResult:
    if not case.forbidden:
        return CheckResult("no_forbidden_terms", True, "none declared")
    texts = recipe_texts(content)
    hits = [term for term in case.forbidden if _mentions(term, texts)]
    return CheckResult("no_forbidden_terms", not hits, f"found: {', '.join(hits) or '-'}")


def check_allergens(case: EvalCase, content: RecipeContent) -> CheckResult:
    allergies = case.profile.allergies if case.profile else []
    if not allergies:
        return CheckResult("no_allergens", True, "no allergies in profile")
    found = find_allergens(allergies, recipe_texts(content))
    return CheckResult("no_allergens", not found, f"found: {', '.join(found) or '-'}")


def check_clarifying_question(case: EvalCase, content: RecipeContent) -> CheckResult:
    asked = content.clarifying_question is not None
    if case.expect_clarifying_question:
        return CheckResult("clarifying_question_asked", asked, "expected a question")
    return CheckResult("no_needless_question", not asked, content.clarifying_question or "-")


def check_steps_usable(_case: EvalCase, content: RecipeContent) -> CheckResult:
    """Steps that are too short to be an instruction usually mean the model padded the list."""
    stubs = [s for s in content.steps if len(s) < 10]
    return CheckResult(
        "steps_usable", not stubs, f"{len(stubs)} stub steps of {len(content.steps)}"
    )


def check_quantities(_case: EvalCase, content: RecipeContent) -> CheckResult:
    """Post-validation invariant, measured so the report can state it held."""
    bad = [i.name for i in content.ingredients if (i.unit is Unit.TO_TASTE) != (i.quantity is None)]
    return CheckResult("quantities_consistent", not bad, f"inconsistent: {', '.join(bad) or '-'}")


CHECKS = (
    check_servings,
    check_uses_user_products,
    check_foreign_ingredients,
    check_have_at_home_honest,
    check_forbidden_terms,
    check_allergens,
    check_clarifying_question,
    check_steps_usable,
    check_quantities,
)


def run_checks(case: EvalCase, content: RecipeContent) -> list[CheckResult]:
    return [check(case, content) for check in CHECKS]
