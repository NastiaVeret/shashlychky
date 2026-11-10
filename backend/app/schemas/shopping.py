from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.allergens import AllergenAlert, AllergenSource

# at_home: the recipe says the user already has it, nothing is looked up
# to_taste: no quantity in the recipe ("за смаком"), nothing to buy
# no_product: Silpo found nothing for this ingredient
# out_of_stock: Silpo knows products for it, but none is available in this store now
# partial_stock: the pick is available, but there is less of it than the recipe needs
# unknown_package: the amount cannot be converted to what Silpo sells (the package is shown as is)
# ok: a product, how much of it to buy, and its price
LineStatus = Literal[
    "at_home", "to_taste", "no_product", "out_of_stock", "partial_stock", "unknown_package", "ok"
]
QuantityUnit = Literal["pack", "kg"]
# How the recipe amount became grams: exact (it was a mass), density (ml via the table),
# density_assumed (the product is not in the table, counted as water), piece_weight (average piece)
GramsBasis = Literal["exact", "density", "density_assumed", "piece_weight"]


class ProductOption(BaseModel):
    """A Silpo product and what Silpo says about how it is sold."""

    product_id: str | None
    name: str
    url: str | None = Field(description="Сторінка товару в Сільпо")
    price: float | None = Field(description="Ціна за упаковку, а для вагових товарів за кг")
    stock: float | None = Field(description="Залишок: упаковок, а для вагових товарів кг")
    weighted: bool
    step: float | None = Field(description="Мінімальний крок: упаковок, а для вагових кг")
    package: str | None = Field(
        description="Що в одній упаковці, як віддає Сільпо: «870г», «10шт». Без перетворень"
    )


class Purchase(BaseModel):
    quantity: float = Field(description="Скільки купити: упаковок або кг (див. quantity_unit)")
    quantity_unit: QuantityUnit
    total_price: float | None
    leftover_g: float | None = Field(description="Скільки грамів лишиться після рецепта")
    leftover_pieces: float | None = Field(description="Скільки штук лишиться після рецепта")
    estimated: bool = Field(
        description="True: вагу оцінено за густиною або середньою вагою штуки, це не точне число"
    )


class Alternative(ProductOption):
    """Another product that could replace the pick. Picking the best one is not done here."""

    enough_stock: bool = Field(description="Чи вистачає цього товару на рецепт")
    purchase: Purchase | None
    allergen_source: AllergenSource
    alerts: list[AllergenAlert] = Field(description="Збіги з алергенами з профілю користувача")


class ShoppingLine(BaseModel):
    name: str
    status: LineStatus
    have_at_home: bool
    quantity: float | None = Field(description="Скільки потрібно за рецептом")
    unit: str = Field(description="Одиниця з рецепта")
    needed_g: float | None = Field(description="Скільки це грамів, якщо вдалося перерахувати")
    grams_basis: GramsBasis | None = Field(description="На чому тримається перерахунок у грами")
    grams_per_unit: float | None = Field(
        description="Грамів на мл (густина) або на штуку, якщо перерахунок оцінений"
    )
    product: ProductOption | None
    purchase: Purchase | None
    alternatives: list[Alternative]


class RecipeShoppingList(BaseModel):
    recipe_id: int
    lines: list[ShoppingLine]
    total_price: float | None = Field(description="Сума за рядками, для яких відомо, що купувати")
    needs_attention: int = Field(description="Рядки, де є проблема: немає, мало або фасування")
