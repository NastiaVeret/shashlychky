"""Grams from a recipe amount: exact for mass, estimated for volume and pieces.

A recipe says "250 мл борошна" or "2 помідори"; a nutrition table and a shop's pack size are in
grams. Millilitres only equal grams for water, and a piece has no weight at all, so both
conversions are estimates and are reported as such (`Grams.basis`) instead of being passed off
as exact. The tables are typical rounded kitchen values, good to roughly ±15 %: they are meant
to stop 250 мл of flour from being counted as 250 г (it is about 130 г), not to weigh anything.

Names are matched by word-prefix regexes against the ingredient name, so "Борошно «Хуторок»
пшеничне" finds "борошно". A name the tables do not know converts to None (pieces) or falls
back to water (volume), and the basis says which.
"""

import re
from dataclasses import dataclass
from typing import Literal

# exact: the unit is a mass; density: millilitres via the table; density_assumed: the table does
# not know the product, so it is counted as water; piece_weight: pieces via the average-piece table
Basis = Literal["exact", "density", "density_assumed", "piece_weight"]

_WORD = re.compile(r"[\w'’]+")

_MASS_G = {"г": 1.0, "гр": 1.0, "кг": 1000.0}
# Volume units in millilitres: a tablespoon is 15 ml, a teaspoon 5 ml.
_VOLUME_ML = {"мл": 1.0, "л": 1000.0, "ст. л.": 15.0, "ст.л.": 15.0, "ч. л.": 5.0, "ч.л.": 5.0}
_PIECES = frozenset({"шт", "шт."})

# An entry matches when EVERY pattern matches some word of the name. First match wins, so the
# specific entries ("цукрова пудра") come before the general ones ("цукор").
_Entry = tuple[tuple[str, ...], float | None]

# g per ml. Checked against USDA FoodData Central (SR Legacy) cup weights / 236.6 ml for flour,
# sugar, powdered sugar, honey, oil, milk, sour cream, rice, salt, cocoa and cornstarch; the rest
# (buckwheat, millet, semolina, oats, breadcrumbs, mayonnaise, ketchup, vinegar) are not checked.
DENSITIES: tuple[_Entry, ...] = (
    ((r"^цукров", r"^пудр"), 0.5),
    ((r"^вод[аиуо]",), 1.0),
    ((r"^молок",), 1.03),
    ((r"^кефір",), 1.03),
    ((r"^йогурт",), 1.03),
    ((r"^вершк",), 1.0),
    ((r"^сметан",), 0.97),
    ((r"^олі",), 0.92),
    ((r"^мед(у|ом)?$",), 1.4),
    ((r"^майонез",), 0.95),
    ((r"^кетчуп",), 1.15),
    ((r"^оцет|^оцту",), 1.01),
    ((r"^борошн",), 0.53),
    ((r"^цукор|^цукру$|^цукром$",), 0.85),
    ((r"^сіл(ь|і|лю)$",), 1.2),
    ((r"^рис(у|ом)?$",), 0.78),
    ((r"^гречк|^гречан",), 0.84),
    ((r"^пшон",), 0.8),
    ((r"^ман(н|к)",), 0.7),
    ((r"^вівсян|^пластівц",), 0.35),
    ((r"^какао",), 0.36),
    ((r"^крохмал",), 0.54),
    ((r"^сухар",), 0.45),
)

# Grams of one medium piece. Tomato, onion, carrot, egg, bell pepper, apple, banana and lemon are
# within USDA's household measures; potato, cucumber, beet, eggplant, zucchini and orange are
# smaller than USDA's (US produce is bigger) and rest on typical Ukrainian sizes, not on a source.
# A None value means "this one has no honest average" and stops the
# search, so green onion is not weighed as bulb onion.
PIECE_GRAMS: tuple[_Entry, ...] = (
    ((r"^цибул", r"^зелен"), None),
    ((r"^помідор",), 120.0),
    ((r"^томат",), 120.0),
    ((r"^огірок|^огірк",), 120.0),
    ((r"^цибул",), 110.0),
    ((r"^картопл",), 120.0),
    ((r"^морк",), 75.0),
    ((r"^буряк",), 200.0),
    ((r"^перец|^перець|^перц", r"^болгарськ|^солодк"), 150.0),
    ((r"^баклажан",), 250.0),
    ((r"^кабачок|^кабачк",), 300.0),
    ((r"^яблук",), 150.0),
    ((r"^груш",), 150.0),
    ((r"^банан",), 120.0),
    ((r"^лимон",), 100.0),
    ((r"^апельсин",), 200.0),
    ((r"^яйц|^яєц",), 55.0),
)


@dataclass(frozen=True, slots=True)
class Grams:
    value: float
    basis: Basis
    # What the estimate rested on: grams per millilitre (density) or per piece. None when exact.
    per_unit: float | None = None


def _lookup(table: tuple[_Entry, ...], name: str) -> float | None:
    words = _WORD.findall(name.casefold())
    for patterns, value in table:
        if all(any(re.search(rx, w) for w in words) for rx in patterns):
            return value
    return None


def density(name: str) -> float | None:
    """Grams per millilitre of the product the name describes, if the table knows it."""
    return _lookup(DENSITIES, name)


def piece_grams(name: str) -> float | None:
    """Average weight of one piece of the product, if the table has an honest figure."""
    return _lookup(PIECE_GRAMS, name)


def to_grams(name: str, quantity: float, unit: str) -> Grams | None:
    """Recipe amount -> grams, or None when there is no honest conversion (unknown unit, a
    piece of something with no average weight)."""
    unit = unit.strip().lower()
    if unit in _MASS_G:
        return Grams(quantity * _MASS_G[unit], "exact")
    if unit in _VOLUME_ML:
        ml = quantity * _VOLUME_ML[unit]
        d = density(name)
        if d is None:
            return Grams(ml, "density_assumed", 1.0)
        return Grams(ml * d, "density", d)
    if unit in _PIECES:
        g = piece_grams(name)
        return None if g is None else Grams(quantity * g, "piece_weight", g)
    return None
