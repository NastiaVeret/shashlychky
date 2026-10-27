"""Insert sample data for local development. Idempotent: skips rows that already exist."""

import asyncio

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.recipe import Recipe
from app.schemas.recipes import Ingredient, RecipeContent

SAMPLE = RecipeContent(
    title="Деруни з цибулею",
    description=(
        "Хрусткі картопляні оладки на пательні. Класика на випадок порожнього холодильника."
    ),
    cooking_time_minutes=35,
    servings=2,
    ingredients=[
        Ingredient(name="Картопля", quantity=600, unit="г", have_at_home=True),
        Ingredient(name="Цибуля", quantity=1, unit="шт", have_at_home=True),
        Ingredient(name="Яйця", quantity=1, unit="шт", have_at_home=True),
        Ingredient(name="Борошно", quantity=2, unit="ст. л.", have_at_home=True),
        Ingredient(name="Сметана", quantity=100, unit="г", have_at_home=False),
        Ingredient(name="Сіль, перець", quantity=None, unit="за смаком", have_at_home=True),
    ],
    steps=[
        "Картоплю і цибулю почистити й натерти на дрібній тертці, відтиснути зайвий сік.",
        "Додати яйце, борошно, сіль і перець, перемішати до однорідної маси.",
        "Розігріти олію на пательні на середньому вогні.",
        "Викладати ложкою невеликі оладки й смажити по 3-4 хвилини з кожного боку.",
        "Подавати гарячими зі сметаною.",
    ],
    tips="Щоб деруни не темніли, тріть картоплю безпосередньо перед смаженням.",
    clarifying_question=None,
)


async def main() -> None:
    async with get_sessionmaker()() as db:
        exists = await db.scalar(select(Recipe.id).where(Recipe.model == "seed").limit(1))
        if exists:
            print(f"seed already present (recipe id {exists})")
            return
        recipe = Recipe(
            products=["яйця", "картопля", "цибуля"],
            preferences=None,
            servings=2,
            model="seed",
            content=SAMPLE.model_dump(mode="json"),
            prompt_tokens=None,
            output_tokens=None,
            latency_ms=0,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)
        print(f"seeded recipe id {recipe.id}: open http://localhost:5173/recipes/{recipe.id}")


if __name__ == "__main__":
    asyncio.run(main())
