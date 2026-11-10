"""Recipe amounts -> packs or kg of a Silpo product (package sizes are real `displayRatio`s)."""

import pytest

from app.integrations.silpo.catalog import Candidate
from app.schemas.recipes import IngredientRead
from app.services.packaging import has_enough_stock, parse_pack, plan_purchase


def product(
    ratio: str | None,
    *,
    price: float | None = 100.0,
    weighted: bool = False,
    step: float | None = 1,
    stock: float | None = 50,
) -> Candidate:
    return Candidate(
        product_id="id",
        name="Товар",
        slug="slug",
        price=price,
        stock=stock,
        available=True,
        weighted=weighted,
        step=step,
        display_ratio=ratio,
    )


def ingredient(quantity: float | None, unit: str, name: str = "x") -> IngredientRead:
    return IngredientRead(name=name, quantity=quantity, unit=unit, have_at_home=False)


@pytest.mark.parametrize(
    ("text", "amount", "kind"),
    [
        ("870г", 870, "weight"),
        ("1,5л", 1500, "volume"),
        ("0.5кг", 500, "weight"),
        ("400 мл", 400, "volume"),
        ("10шт", 10, "count"),
        ("10 шт", 10, "count"),
    ],
)
def test_parse_pack_reads_silpo_wording(text: str, amount: float, kind: str) -> None:
    pack = parse_pack(text)
    assert pack is not None and (pack.amount, pack.kind) == (amount, kind)


@pytest.mark.parametrize(
    "text", [None, "", "шт", "2х150г", "набір", "5 порцій", "0г", "0шт", "0,0л", "0 кг"]
)
def test_parse_pack_refuses_what_it_cannot_read(text: str | None) -> None:
    assert parse_pack(text) is None


@pytest.mark.parametrize(
    ("ing", "ratio"), [(ingredient(300, "г"), "0г"), (ingredient(3, "шт"), "0шт")]
)
def test_an_empty_pack_has_no_purchase_instead_of_dividing_by_zero(
    ing: IngredientRead, ratio: str
) -> None:
    assert plan_purchase(ing, product(ratio)) is None


# ---------- counted packs: eggs "10шт" ----------


def test_three_eggs_need_one_pack_of_ten() -> None:
    p = plan_purchase(ingredient(3, "шт"), product("10шт", price=138.03))
    assert p is not None
    assert (p.quantity, p.quantity_unit, p.total_price) == (1, "pack", 138.03)
    assert p.leftover_pieces == 7 and p.leftover_g is None


def test_twelve_eggs_need_two_packs() -> None:
    p = plan_purchase(ingredient(12, "шт"), product("10шт", price=138.03))
    assert p is not None and p.quantity == 2 and p.total_price == 276.06


# ---------- weight / volume packs ----------


@pytest.mark.parametrize(
    ("quantity", "unit", "ratio", "packs", "leftover_g"),
    [
        (200, "г", "300г", 1, 100),
        (400, "г", "300г", 2, 200),
        (900, "г", "300г", 3, 0),  # an exact fit does not buy an extra pack
        (250, "мл", "870г", 1, 620),  # millilitres count as grams, as in КБЖВ
        (2, "ст. л.", "300г", 1, 270),
        (3, "ч. л.", "300г", 1, 285),
        (3300, "мл", "1,1л", 3, 0),  # 1.1 * 1000 is not exactly 1100 in floating point
    ],
)
def test_weight_and_volume_round_up_to_whole_packs(
    quantity: float, unit: str, ratio: str, packs: int, leftover_g: float
) -> None:
    p = plan_purchase(ingredient(quantity, unit), product(ratio, price=10))
    assert p is not None
    assert (p.quantity, p.leftover_g) == (packs, leftover_g)
    assert p.total_price == packs * 10


# ---------- weighted goods: kg and a step ----------


def test_weighted_rounds_up_to_the_step() -> None:
    # real card: varena sausage, 364 per kg, step 0.65
    p = plan_purchase(ingredient(200, "г"), product("100г", price=364, weighted=True, step=0.65))
    assert p is not None
    assert (p.quantity, p.quantity_unit, p.total_price) == (0.65, "kg", 236.6)
    assert p.leftover_g == 450


def test_weighted_more_than_one_step() -> None:
    p = plan_purchase(ingredient(1500, "г"), product("100г", price=364, weighted=True, step=0.65))
    assert p is not None and p.quantity == 1.95


def test_weighted_with_a_fine_step_buys_close_to_the_need() -> None:
    p = plan_purchase(ingredient(500, "г"), product("100г", price=246.17, weighted=True, step=0.05))
    assert p is not None and p.quantity == 0.5 and p.total_price == 123.09  # real: 0.5 kg fillet


# ---------- never guess ----------


@pytest.mark.parametrize(
    ("ing", "prod"),
    [
        (ingredient(4, "шт"), product("2кг")),  # pieces vs a bag of unknown piece weight
        (
            ingredient(2, "шт"),
            product("100г", weighted=True, step=0.1),
        ),  # pieces of a weighted good
        (ingredient(200, "г"), product("10шт")),  # grams vs a pack counted in pieces
        (ingredient(200, "г"), product("2х150г")),  # multipack
        (ingredient(200, "г"), product(None)),
        (ingredient(None, "за смаком"), product("300г")),
        (ingredient(1, "пучок"), product("300г")),  # not a convertible unit
        (ingredient(200, "г"), product("100г", weighted=True, step=None)),  # no step to round to
    ],
)
def test_no_honest_conversion_means_no_purchase(ing: IngredientRead, prod: Candidate) -> None:
    assert plan_purchase(ing, prod) is None


# ---------- stock ----------


def test_stock_shortage_is_known_only_from_a_known_stock() -> None:
    p = plan_purchase(ingredient(900, "г"), product("300г", stock=2))
    assert p is not None and p.quantity == 3
    assert has_enough_stock(p, product("300г", stock=2)) is False
    assert has_enough_stock(p, product("300г", stock=3)) is True
    assert has_enough_stock(p, product("300г", stock=None)) is True


# ---------- densities and piece weights (the estimates) ----------


def test_flour_by_volume_is_weighed_with_its_density() -> None:
    # 250 ml of flour is ~132 g, so one 1 kg bag with 867 g to spare, not "250 g of flour"
    p = plan_purchase(ingredient(250, "мл", "Борошно"), product("1кг", price=34.99))
    assert p is not None and p.quantity == 1 and p.leftover_g == 867.5 and p.estimated is True


def test_milk_by_volume_against_a_pack_in_grams() -> None:
    # real card: Galychyna milk "950г"; 250 ml of milk is 257.5 g
    p = plan_purchase(ingredient(250, "мл", "Молоко"), product("950г", price=75.49))
    assert p is not None and p.quantity == 1 and p.leftover_g == 692.5


def test_oil_in_grams_against_a_pack_in_millilitres() -> None:
    p = plan_purchase(ingredient(100, "г", "Олія"), product("850мл", price=80))
    assert p is not None and p.quantity == 1 and p.leftover_g == 682
    assert p.estimated is True  # the bottle's content is weighed with the table density


def test_exact_mass_against_exact_mass_is_not_an_estimate() -> None:
    p = plan_purchase(ingredient(200, "г", "Борошно"), product("1кг"))
    assert p is not None and p.estimated is False


def test_pieces_of_a_weighted_good_use_the_average_piece() -> None:
    # 2 tomatoes = 240 g, sold by weight with a 0.05 kg step -> 0.25 kg
    p = plan_purchase(ingredient(2, "шт", "Помідор"), product("100г", weighted=True, step=0.05))
    assert p is not None and (p.quantity, p.quantity_unit, p.estimated) == (0.25, "kg", True)


def test_pieces_against_a_bag_in_kg_use_the_average_piece() -> None:
    # 4 potatoes = 480 g: one 2 kg bag, not four bags
    p = plan_purchase(ingredient(4, "шт", "Картопля"), product("2кг"))
    assert p is not None and (p.quantity, p.quantity_unit) == (1, "pack")


def test_pieces_with_no_average_weight_stay_unconverted() -> None:
    assert plan_purchase(ingredient(3, "шт", "Часник"), product("100г", weighted=True)) is None
