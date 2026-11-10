"""Millilitres and pieces to grams: typical kitchen figures, always reported as estimates."""

import pytest

from app.services.units import density, piece_grams, to_grams


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Борошно «Хуторок» пшеничне", 0.53),
        ("Молоко «Галичина» ультрапастеризоване 2,5%", 1.03),
        ("Олія соняшникова", 0.92),
        ("Цукор-пісок", 0.85),
        ("Цукрова пудра", 0.5),  # before plain sugar
        ("Мед", 1.4),
        ("Сіль", 1.2),
        ("Вода", 1.0),
    ],
)
def test_density_of_common_products(name: str, expected: float) -> None:
    assert density(name) == expected


@pytest.mark.parametrize("name", ["Медальйони", "Помідор", "Кіноа", "Рисова локшина"])
def test_density_ignores_lookalikes_and_unknowns(name: str) -> None:
    assert density(name) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Помідор", 120),
        ("Помідори черрі", 120),
        ("Цибуля ріпчаста", 110),
        ("Картопля", 120),
        ("Перець болгарський", 150),
        ("Яйця курячі", 55),
    ],
)
def test_piece_weight_of_common_produce(name: str, expected: float) -> None:
    assert piece_grams(name) == expected


@pytest.mark.parametrize("name", ["Цибуля зелена", "Перець чорний", "Часник", "Кіноа"])
def test_no_honest_piece_weight_means_none(name: str) -> None:
    assert piece_grams(name) is None


def test_mass_is_exact() -> None:
    g = to_grams("Борошно", 200, "г")
    assert g is not None and (g.value, g.basis, g.per_unit) == (200, "exact", None)


def test_flour_by_volume_is_not_counted_as_water() -> None:
    # a 250 ml cup of flour is about 130 g, not 250
    g = to_grams("Борошно", 250, "мл")
    assert g is not None and g.basis == "density"
    assert g.value == pytest.approx(132.5) and g.per_unit == 0.53


def test_spoons_use_the_density_too() -> None:
    g = to_grams("Олія", 2, "ст. л.")
    assert g is not None and g.value == pytest.approx(27.6) and g.basis == "density"


def test_unknown_liquid_falls_back_to_water_and_says_so() -> None:
    g = to_grams("Квас", 300, "мл")
    assert g is not None and (g.value, g.basis, g.per_unit) == (300, "density_assumed", 1.0)


def test_pieces_use_the_average_piece() -> None:
    g = to_grams("Помідор", 2, "шт")
    assert g is not None and (g.value, g.basis, g.per_unit) == (240, "piece_weight", 120)


@pytest.mark.parametrize(
    ("name", "quantity", "unit"),
    [("Часник", 3, "шт"), ("Сіль", 1, "за смаком"), ("Розмарин", 1, "пучок")],
)
def test_no_conversion_when_there_is_no_honest_one(name: str, quantity: float, unit: str) -> None:
    assert to_grams(name, quantity, unit) is None
