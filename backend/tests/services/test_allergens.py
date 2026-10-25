import pytest

from app.services.allergens import find_allergens, recipe_texts
from tests.conftest import SAMPLE_RECIPE


@pytest.mark.parametrize(
    ("allergy", "text"),
    [
        ("арахіс", "Арахісова паста"),
        ("яйця", "Яйце куряче"),
        ("горіхи", "посипати волоськими горіхами"),
        ("молоко", "молочний соус"),
        ("кунжут", "кунжутна олія"),
        ("мед", "медова заправка"),
        ("морепродукти", "Морепродукти заморожені"),
        ("коров'яче молоко", "коров'яче молоко 2,5%"),
    ],
)
def test_find_allergens_matches_inflected_forms(allergy: str, text: str) -> None:
    assert find_allergens([allergy], [text]) == [allergy]


@pytest.mark.parametrize(
    ("allergy", "text"),
    [
        ("мед", "камедь"),  # only word starts count, not substrings in the middle
        ("арахіс", "рис"),
        ("коров'яче молоко", "кокосове молоко"),  # every word of the allergy must match
    ],
)
def test_find_allergens_ignores_unrelated_words(allergy: str, text: str) -> None:
    assert find_allergens([allergy], [text]) == []


def test_recipe_texts_cover_ingredients_and_steps() -> None:
    texts = recipe_texts(SAMPLE_RECIPE)

    assert "Яйця" in texts
    assert "Нарізати помідор." in texts
