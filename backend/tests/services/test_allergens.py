import pytest

from app.schemas.recipes import Ingredient, RecipeContent
from app.services.allergens import find_allergens, recipe_texts
from tests.conftest import SAMPLE_RECIPE


@pytest.mark.parametrize(
    ("allergy", "text"),
    [
        ("арахіс", "Арахісова паста"),
        ("яйця", "Яйце куряче"),
        ("яйця", "3 яєць"),
        ("яйця", "яєчня з помідорами"),
        ("яйця", "яєчний жовток"),
        ("горіхи", "посипати волоськими горіхами"),
        ("горіхи", "горіхова паста"),
        ("молоко", "молочний соус"),
        ("молоко", "залити молоком"),
        ("кунжут", "кунжутна олія"),
        ("мед", "медова заправка"),
        ("мед", "ложка меду"),
        ("соя", "соєвий соус"),
        ("курка", "куряче філе"),
        ("курка", "курятина"),
        ("риба", "рибний бульйон"),
        ("сир", "сирний соус"),
        ("сир", "тертий сир"),
        ("морепродукти", "Морепродукти заморожені"),
        ("коров'яче молоко", "коров'яче молоко 2,5%"),
        ("пшениця", "пшеничне борошно"),
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
        # everyday words that merely share a prefix with an allergen
        ("молоко", "перець чорний молотий"),
        ("молоко", "молода картопля"),
        ("сир", "сирий"),
        ("мед", "медальйони зі свинини"),
        ("мак", "макарони"),
        ("мак", "макрель"),
        ("масло", "маслини"),
        ("горіхи", "горілка"),
        ("соя", "сосиски"),
        ("рис", "риба"),
        ("риба", "рис"),
    ],
)
def test_find_allergens_ignores_unrelated_words(allergy: str, text: str) -> None:
    assert find_allergens([allergy], [text]) == []


def test_recipe_texts_cover_every_field_an_allergen_can_hide_in() -> None:
    content = RecipeContent(
        title="Омлет з сиром",
        description="Сніданок з горіховою посипкою.",
        cooking_time_minutes=10,
        servings=1,
        ingredients=[Ingredient(name="Яйця", quantity=2, unit="шт", have_at_home=True)],
        steps=["Збити яйця."],
        tips="Подавайте з медом.",
    )

    texts = recipe_texts(content)

    assert find_allergens(["сир"], texts) == ["сир"]  # title
    assert find_allergens(["горіхи"], texts) == ["горіхи"]  # description
    assert find_allergens(["мед"], texts) == ["мед"]  # tips
    assert "Яйця" in recipe_texts(SAMPLE_RECIPE)
    assert "Нарізати помідор." in recipe_texts(SAMPLE_RECIPE)
