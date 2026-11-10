"""Finds a few real Silpo products whose card has a non-empty "Містить алергени" attribute.

A dev probe for fixtures and parser checks, not a crawler: it asks for a handful of everyday
product types, reads at most `--max-cards` cards and stops as soon as it has `--count` hits
(Silpo's terms forbid mass collection of its range, so keep both numbers small and do not save
the output anywhere but a test fixture or two). Read-only; needs a login first.

    SILPO_MCP_URL=https://mcp.silpo.ua/mcp uv run python -m scripts.silpo_find_allergen_products
    ... --count 8 --max-cards 30
"""

import asyncio
import os
import sys

from app.integrations.silpo import connect
from app.integrations.silpo.catalog import ProductCatalog
from app.services.product_allergens import ATTR_ALLERGENS, parse_allergen_attribute

URL = os.environ.get("SILPO_MCP_URL", "https://mcp.silpo.ua/mcp")

# Everyday products that usually carry an allergen declaration, most likely first.
QUERIES = [
    "ковбаса варена",
    "сосиски",
    "печиво",
    "шоколадний батончик",
    "йогурт",
    "паштет",
    "кетчуп",
    "соєвий соус",
    "макарони",
    "хліб",
]


def option(name: str, default: int) -> int:
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


async def main() -> None:
    wanted, max_cards = option("--count", 5), option("--max-cards", 25)
    found = fetched = 0
    async with connect(URL) as silpo:
        catalog = ProductCatalog(silpo)
        for query in QUERIES:
            if found >= wanted or fetched >= max_cards:
                break
            hits = (await catalog.match([query]))[query].candidates
            batch = [c for c in hits if c.available][: max_cards - fetched]
            fetched += len(batch)
            cards = await catalog.cards(batch)
            for candidate in batch:
                card = cards[candidate.slug]
                text = card.attributes.get(ATTR_ALLERGENS)
                if not (isinstance(text, str) and text.strip()):
                    continue
                found += 1
                contains, traces = parse_allergen_attribute(text) or ([], [])
                print(f"\n[{query}] {candidate.name}")
                print(f"  {card.url}")
                print(f"  поле:   {text!r}")
                print(f"  розбір: містить={contains} сліди={traces}")
                if found >= wanted:
                    break
    print(f"\nЗнайдено {found} з {wanted}, прочитано карток: {fetched}")


asyncio.run(main())
