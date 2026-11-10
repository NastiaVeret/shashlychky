"""What Silpo sells for a recipe's ingredients: one shared lookup behind КБЖВ, allergens and the
shopping list.

All three checks read the same product cards. Fetching a card once per request, with the number
of parallel calls capped, keeps the load on Silpo down: it answers 0.2 s to one search but 4.2 s
when 40 run at once. Everything is memoised for the lifetime of one `ProductCatalog` only, i.e.
one request: nothing here builds a catalogue of Silpo's range (forbidden by its terms of use).
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

# Search results kept per ingredient: the first available one is the pick, the rest are the
# pool for substitutes when the pick is short on stock.
CANDIDATES_PER_INGREDIENT = 5
# Product cards fetched in parallel. Well below the 40 that slowed Silpo down in measurements.
CARD_CONCURRENCY = 3
# Upper bound for everything one request asks Silpo. Each call also has its own timeout, and a
# lookup is one search plus several cards, so without this the worst case is minutes.
LOOKUP_DEADLINE_SECONDS = 25.0


class SilpoSession(Protocol):
    """The subset of `SilpoClient` this module needs. Values are raw MCP JSON, hence Any."""

    async def search_context(self) -> dict[str, Any]: ...

    async def find_products(
        self, names: list[str], limit: int = 3, ctx: dict[str, Any] | None = None
    ) -> dict[str, list[Any]]: ...

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Candidate:
    """A product as a search result lists it: enough to price and pack it, not to vet it."""

    product_id: str | None
    name: str
    slug: str
    price: float | None
    stock: float | None  # pieces, or kg for weighted goods
    available: bool
    weighted: bool
    step: float | None  # smallest increment: pieces, or kg for weighted goods
    display_ratio: str | None  # what one unit holds, as Silpo prints it: "870г", "10шт"

    @classmethod
    def from_search(cls, item: dict[str, Any]) -> "Candidate":
        return cls(
            product_id=item.get("id"),
            name=str(item.get("name", "")),
            slug=str(item.get("slug", "")),
            price=item.get("price"),
            stock=item.get("stock"),
            available=bool(item.get("available")),
            weighted=bool(item.get("weighted")),
            step=item.get("step"),
            display_ratio=item.get("displayRatio"),
        )


@dataclass(frozen=True, slots=True)
class ProductCard:
    """A candidate plus its detail card (nutrition, allergens, link to the product page)."""

    candidate: Candidate
    url: str | None
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IngredientMatch:
    name: str
    candidates: list[Candidate]  # every search result, best first
    card: ProductCard | None  # card of the first available candidate; None when none is available


class ProductCatalog:
    """Product lookups over one Silpo session, memoised per instance (= per request)."""

    def __init__(self, silpo: SilpoSession) -> None:
        self._silpo = silpo
        self._ctx: dict[str, Any] | None = None
        self._cards: dict[str, ProductCard] = {}

    async def context(self) -> dict[str, Any]:
        """Store, delivery type and a currently valid slot; fetched once, shared by all calls."""
        if self._ctx is None:
            self._ctx = await self._silpo.search_context()
        return self._ctx

    async def match(self, names: list[str]) -> dict[str, IngredientMatch]:
        """One batch search for every name, then the card of each name's first available hit."""
        ctx = await self.context()
        found = await self._silpo.find_products(names, limit=CANDIDATES_PER_INGREDIENT, ctx=ctx)
        candidates = {n: [Candidate.from_search(p) for p in found.get(n, [])] for n in names}
        picks = {n: next((c for c in cs if c.available), None) for n, cs in candidates.items()}
        cards = await self.cards([c for c in picks.values() if c is not None])
        return {
            n: IngredientMatch(
                name=n,
                candidates=candidates[n],
                card=cards[pick.slug] if (pick := picks[n]) else None,
            )
            for n in names
        }

    async def cards(self, candidates: list[Candidate]) -> dict[str, ProductCard]:
        """Cards by slug. Already fetched ones are reused; the rest are fetched in parallel,
        at most `CARD_CONCURRENCY` at a time. The first failure is raised."""
        missing = {c.slug: c for c in candidates if c.slug not in self._cards}
        if missing:
            ctx = await self.context()
            gate = asyncio.Semaphore(CARD_CONCURRENCY)

            async def fetch(candidate: Candidate) -> ProductCard:
                async with gate:
                    res = await self._silpo.call(
                        "silpo_get_product_details", {**ctx, "slug": candidate.slug}
                    )
                card = res.get("product") or {}
                return ProductCard(candidate, card.get("url"), card.get("attributes") or {})

            results = await asyncio.gather(
                *(fetch(c) for c in missing.values()), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            self._cards.update({r.candidate.slug: r for r in results if isinstance(r, ProductCard)})
        return {c.slug: self._cards[c.slug] for c in candidates}

    async def similar(self, candidate: Candidate, limit: int = 5) -> list[Candidate]:
        """Silpo's own alternatives to a product, in the same store and slot."""
        ctx = await self.context()
        res = await self._silpo.call(
            "silpo_get_similar_products", {**ctx, "slug": candidate.slug, "limit": limit}
        )
        return [Candidate.from_search(p) for p in res.get("products", [])]
