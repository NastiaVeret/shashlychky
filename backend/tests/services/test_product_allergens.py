"""Allergens hiding in products: Silpo's card attribute first, a short dictionary as a hint."""

from typing import Any

import pytest

from app.integrations.silpo.catalog import Candidate, IngredientMatch, ProductCard
from app.services.allergens import find_allergens
from app.services.product_allergens import (
    ATTR_ALLERGENS,
    build_allergen_check,
    check_ingredient,
    likely_allergens,
    parse_allergen_attribute,
)
from tests.conftest import SAMPLE_RECIPE

# Verbatim from a real silpo_get_product_details answer (Український м'ясокомбінат, варена ковбаса)
SAUSAGE_ALLERGENS = "ЯЙЦЯ.  Може містити сліди: ГІРЧИЦЮ, СЕЛЕРУ, СОЮ, МОЛОКО."


def match(name: str, attributes: dict[str, Any] | None, *, url: str | None = "https://p") -> Any:
    """An IngredientMatch whose picked product has the given card attributes (None: no product)."""
    if attributes is None:
        return IngredientMatch(name=name, candidates=[], card=None)
    candidate = Candidate(
        product_id="id",
        name=name,
        slug="slug",
        price=1.0,
        stock=5,
        available=True,
        weighted=False,
        step=1,
        display_ratio="1шт",
    )
    return IngredientMatch(
        name=name, candidates=[candidate], card=ProductCard(candidate, url, attributes)
    )


# ---------- the card attribute ----------


def test_parse_splits_declared_allergens_from_traces() -> None:
    assert parse_allergen_attribute(SAUSAGE_ALLERGENS) == (
        ["яйця"],
        ["гірчицю", "селеру", "сою", "молоко"],
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("МОЛОКО, ЯЙЦЯ", (["молоко", "яйця"], [])),
        ("Містить: пшениця; соя", (["пшениця", "соя"], [])),
        ("Може містити сліди: ГОРІХИ", ([], ["горіхи"])),
        ("МОЛОКО. Може містити: СОЮ", (["молоко"], ["сою"])),
    ],
)
def test_parse_handles_the_other_wordings(
    value: str, expected: tuple[list[str], list[str]]
) -> None:
    assert parse_allergen_attribute(value) == expected


@pytest.mark.parametrize("value", [None, "", "   ", 5, ["яйця"]])
def test_parse_returns_none_without_usable_text(value: object) -> None:
    assert parse_allergen_attribute(value) is None


def test_silpo_wordings_match_the_users_allergy_names() -> None:
    # accusative forms as Silpo prints them must still meet the nominative in a profile
    assert find_allergens(["соя", "гірчиця", "селера", "молоко"], ["сою", "гірчицю", "селеру"]) == [
        "соя",
        "гірчиця",
        "селера",
    ]


# ---------- the dictionary ----------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Майонез «Щедро» «Провансаль» 67%", ["яйця", "гірчиця"]),
        ("Шоколад молочний Milka без добавок", ["молоко"]),
        ("Вершки 10%", ["молоко"]),
        ("Сир кисломолочний", ["молоко"]),
        ("Спагеті", ["глютен", "пшениця"]),
        ("Хліб житній", ["глютен", "пшениця"]),
        ("Борошно «Хуторок» пшеничне", ["глютен", "пшениця"]),
    ],
)
def test_dictionary_knows_typical_allergens(name: str, expected: list[str]) -> None:
    assert likely_allergens(name) == expected


@pytest.mark.parametrize("name", ["Сирий фарш", "Хлібці", "Помідор", "Шоколад чорний", "Яйця"])
def test_dictionary_stays_quiet_for_lookalikes_and_plain_products(name: str) -> None:
    assert likely_allergens(name) == []


# ---------- one ingredient ----------


def test_card_with_allergens_is_declared_and_alerts_the_user() -> None:
    row = check_ingredient(
        "Ковбаса", match("Ковбаса", {ATTR_ALLERGENS: SAUSAGE_ALLERGENS}), ["яйця", "молоко", "риба"]
    )
    assert row.source == "declared"
    assert row.contains == ["яйця"] and "молоко" in row.traces
    assert [(a.allergy, a.level) for a in row.alerts] == [
        ("яйця", "contains"),
        ("молоко", "traces"),
    ]
    assert row.product_url == "https://p"


def test_declared_card_wins_over_the_dictionary() -> None:
    # the card is the source of truth: no dictionary guess is mixed in
    row = check_ingredient("Майонез", match("Майонез", {ATTR_ALLERGENS: "ГІРЧИЦЯ"}), ["яйця"])
    assert row.source == "declared" and row.likely == [] and row.alerts == []


def test_hidden_egg_in_mayonnaise_is_flagged_as_likely() -> None:
    # the case of the risk table: a card without allergens and an allergy to eggs
    row = check_ingredient("Майонез", match("Майонез «Щедро»", {"Країна": "Україна"}), ["яйця"])
    assert row.source == "likely"
    assert [(a.allergy, a.level) for a in row.alerts] == [("яйця", "likely")]


def test_ingredient_the_dictionary_knows_is_flagged_even_without_a_product() -> None:
    row = check_ingredient("Майонез", match("Майонез", None), ["яйця"])
    assert row.source == "likely" and row.product_url is None
    assert [a.level for a in row.alerts] == ["likely"]


def test_a_product_named_after_the_allergen_alerts_even_with_no_card_data() -> None:
    # real run: eggs and milk came back "unknown" with no alert for a user allergic to both
    row = check_ingredient("Яйця", match("Яйця курячі Шаничі С0", {}), ["яйця", "молоко"])
    assert row.source == "unknown"
    assert [(a.allergy, a.level) for a in row.alerts] == [("яйця", "contains")]


def test_nothing_known_is_unknown_never_safe() -> None:
    row = check_ingredient("Помідор", match("Помідор", {"Країна": "Україна"}), ["яйця"])
    assert row.source == "unknown" and row.alerts == []
    assert row.product_url == "https://p"  # the user is pointed to the page to check the label


def test_a_declared_card_with_other_allergens_raises_no_alert() -> None:
    row = check_ingredient(
        "Ковбаса", match("Ковбаса", {ATTR_ALLERGENS: SAUSAGE_ALLERGENS}), ["арахіс"]
    )
    assert row.source == "declared" and row.alerts == []


# ---------- the whole recipe ----------


def test_recipe_check_counts_unknowns_and_alerts() -> None:
    matches = {
        "Яйця": match("Яйця", {ATTR_ALLERGENS: "ЯЙЦЯ"}),
        "Помідор": match("Помідор", {}),
    }
    check = build_allergen_check(1, SAMPLE_RECIPE, matches, ["яйця"], silpo_checked=True)

    assert [r.name for r in check.ingredients] == ["Яйця", "Помідор", "Сіль"]
    assert check.unknown_ingredients == 2  # tomato and salt (no product)
    assert check.has_alerts and check.profile_applied and check.silpo_checked


def test_anonymous_check_has_no_alerts_but_still_reports_what_is_declared() -> None:
    matches = {"Яйця": match("Яйця", {ATTR_ALLERGENS: "ЯЙЦЯ"})}
    check = build_allergen_check(1, SAMPLE_RECIPE, matches, None, silpo_checked=True)
    assert not check.profile_applied and not check.has_alerts
    assert check.ingredients[0].contains == ["яйця"]


def test_an_attribute_with_nothing_readable_is_treated_as_no_data() -> None:
    row = check_ingredient("Напій", match("Напій", {ATTR_ALLERGENS: " . "}), [])
    assert row.source == "unknown" and row.contains == [] and row.traces == []


def test_traces_only_still_count_as_declared_data() -> None:
    row = check_ingredient(
        "Печиво", match("Печиво", {ATTR_ALLERGENS: "Може містити сліди: СОЮ"}), []
    )
    assert row.source == "declared" and row.contains == [] and row.traces == ["сою"]
