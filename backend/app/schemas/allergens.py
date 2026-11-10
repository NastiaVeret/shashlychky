from typing import Literal

from pydantic import BaseModel, Field

# declared: Silpo's product card lists allergens (the only data source)
# likely: the card says nothing, but products of this type usually contain them (our own short
#         dictionary: a hint, not a fact)
# unknown: nothing is known; the user must check the product page
AllergenSource = Literal["declared", "likely", "unknown"]
# contains: listed as an ingredient; traces: "may contain traces of"; likely: the dictionary guess
AlertLevel = Literal["contains", "traces", "likely"]


class AllergenAlert(BaseModel):
    allergy: str = Field(description="Алерген з профілю користувача, який збігся")
    level: AlertLevel


class IngredientAllergens(BaseModel):
    name: str
    source: AllergenSource
    product_name: str | None = Field(description="Товар Сільпо, чию картку перевірено")
    product_url: str | None = Field(description="Сторінка товару в Сільпо: перевірити склад самому")
    contains: list[str] = Field(description="Алергени, які вказані як склад у картці Сільпо")
    traces: list[str] = Field(description="Алергени, сліди яких можливі за декларацією")
    likely: list[str] = Field(description="Імовірні алергени за типом продукту (підказка)")
    alerts: list[AllergenAlert] = Field(description="Збіги з алергенами з профілю користувача")


class RecipeAllergenCheck(BaseModel):
    recipe_id: int
    profile_applied: bool = Field(description="Чи враховано алергени з профілю (є вхід)")
    silpo_checked: bool = Field(
        description="False: Сільпо не відповіло, показано лише підказки за типом продукту"
    )
    ingredients: list[IngredientAllergens]
    unknown_ingredients: int = Field(description="Інгредієнти, про алергени яких нічого не відомо")
    has_alerts: bool
