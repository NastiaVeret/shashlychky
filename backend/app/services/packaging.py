"""From what a recipe needs to what Silpo sells: how many packs (or how many kg) to buy.

Pure functions, no I/O. Silpo prints the content of one unit as text (`displayRatio`: "870г",
"1,5л", "10шт"); this module reads it and does the arithmetic, and says nothing when it cannot be
sure. A wrong guess costs the user a useless purchase, so every case without an honest conversion
returns None and the caller shows Silpo's own wording of the package instead.
"""

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.integrations.silpo.catalog import Candidate
from app.schemas.recipes import IngredientRead
from app.schemas.shopping import Purchase
from app.services.units import density, to_grams

_PACK = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(г|кг|мл|л|шт)\.?\s*$", re.IGNORECASE)
_PACK_FACTOR = {"г": 1.0, "кг": 1000.0, "мл": 1.0, "л": 1000.0}


@dataclass(frozen=True, slots=True)
class Pack:
    amount: float  # grams for "weight", millilitres for "volume", pieces for "count"
    kind: Literal["weight", "volume", "count"]


def parse_pack(display_ratio: str | None) -> Pack | None:
    """ "870г" -> 870 g, "1,5л" -> 1500 ml, "10шт" -> 10 pieces; multipacks, text, "0г" -> None."""
    if not display_ratio or not (m := _PACK.match(display_ratio)):
        return None
    amount, unit = float(m.group(1).replace(",", ".")), m.group(2).lower()
    if amount <= 0:  # "0г": nothing honest to divide by
        return None
    if unit == "шт":
        return Pack(amount, "count")
    return Pack(amount * _PACK_FACTOR[unit], "weight" if unit in ("г", "кг") else "volume")


def _ceil(value: float) -> int:
    return math.ceil(round(value, 6))  # 3.0000000000000004 must not become 4


def _round_up_to_step(value: float, step: float) -> float:
    return round(_ceil(value / step) * step, 3)


def _price(unit_price: float | None, quantity: float) -> float | None:
    """Money in decimals, half-up (Silpo: 0.5 kg at 246.17 is 123.09; float `round` says 123.08)."""
    if unit_price is None:
        return None
    total = Decimal(str(unit_price)) * Decimal(str(quantity))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def plan_purchase(ingredient: IngredientRead, product: Candidate) -> Purchase | None:
    """How much of `product` covers the ingredient, or None when no honest conversion exists.

    Amounts in millilitres or pieces are converted through the density and piece-weight tables
    of `app.services.units`; the result then carries `estimated=True`."""
    if ingredient.quantity is None:
        return None
    needed = to_grams(ingredient.name, ingredient.quantity, ingredient.unit)
    pack = None if product.weighted else parse_pack(product.display_ratio)

    if product.weighted:
        # Sold by weight: quantity and step are in kg.
        if needed is None or not product.step:
            return None
        kg = _round_up_to_step(needed.value / 1000, product.step)
        return Purchase(
            quantity=kg,
            quantity_unit="kg",
            total_price=_price(product.price, kg),
            leftover_g=round(kg * 1000 - needed.value, 1),
            leftover_pieces=None,
            estimated=needed.basis != "exact",
        )

    if pack is None:
        return None
    if pack.kind == "count":
        # "3 шт" is only comparable with a pack counted in pieces ("10шт")
        if ingredient.unit.strip().lower() not in ("шт", "шт."):
            return None
        packs = _ceil(ingredient.quantity / pack.amount)
        return Purchase(
            quantity=packs,
            quantity_unit="pack",
            total_price=_price(product.price, packs),
            leftover_g=None,
            leftover_pieces=round(packs * pack.amount - ingredient.quantity, 3),
            estimated=False,
        )

    if needed is None:
        return None
    # A volume pack ("850мл") is weighed with the same density as the recipe amount.
    pack_density = 1.0 if pack.kind == "weight" else density(ingredient.name) or 1.0
    pack_g = pack.amount * pack_density
    packs = _ceil(needed.value / pack_g)
    return Purchase(
        quantity=packs,
        quantity_unit="pack",
        total_price=_price(product.price, packs),
        leftover_g=round(packs * pack_g - needed.value, 1),
        leftover_pieces=None,
        estimated=needed.basis != "exact" or pack.kind == "volume",
    )


def has_enough_stock(purchase: Purchase, product: Candidate) -> bool:
    """Unknown stock is not a shortage: only a known, smaller stock counts."""
    return product.stock is None or purchase.quantity <= product.stock
