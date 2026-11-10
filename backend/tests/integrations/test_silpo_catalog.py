"""Shared product lookup: one batch search, capped parallel card fetches, memoised per request."""

import asyncio
from typing import Any

import pytest

from app.integrations.silpo import SilpoError
from app.integrations.silpo.catalog import CARD_CONCURRENCY, Candidate, ProductCatalog

CTX = {"branchId": "b", "deliveryType": "DeliveryHome"}


def hit(slug: str, *, available: bool = True, **extra: Any) -> dict[str, Any]:
    return {"id": f"id-{slug}", "name": slug.title(), "slug": slug, "available": available, **extra}


class FakeSilpo:
    """Mimics SilpoClient. `catalogue` maps a search query to its hits."""

    def __init__(self, catalogue: dict[str, list[dict[str, Any]]], *, delay: float = 0) -> None:
        self.catalogue = catalogue
        self.delay = delay
        self.context_calls = 0
        self.search_calls: list[list[str]] = []
        self.detail_calls: list[str] = []
        self.running = 0
        self.max_running = 0
        self.broken_slugs: set[str] = set()

    async def search_context(self) -> dict[str, Any]:
        self.context_calls += 1
        return CTX

    async def find_products(
        self, names: list[str], limit: int = 3, ctx: dict[str, Any] | None = None
    ) -> dict[str, list[Any]]:
        self.search_calls.append(names)
        return {n: self.catalogue.get(n, [])[:limit] for n in names}

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        assert args is not None
        if name == "silpo_get_similar_products":
            return {"products": [hit("alt")]}
        assert name == "silpo_get_product_details"
        self.detail_calls.append(args["slug"])
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            if args["slug"] in self.broken_slugs:
                raise SilpoError(name, "card is broken")
            return {
                "product": {"url": f"https://silpo.ua/product/{args['slug']}", "attributes": {}}
            }
        finally:
            self.running -= 1


async def test_match_searches_once_and_picks_first_available_with_its_card() -> None:
    silpo = FakeSilpo(
        {"молоко": [hit("gone", available=False), hit("milk")], "сир": [hit("cheese")]}
    )
    matches = await ProductCatalog(silpo).match(["молоко", "сир", "кіноа"])

    assert silpo.search_calls == [["молоко", "сир", "кіноа"]]
    assert matches["молоко"].card is not None
    assert matches["молоко"].card.candidate.slug == "milk"
    assert matches["молоко"].card.url == "https://silpo.ua/product/milk"
    assert [c.slug for c in matches["молоко"].candidates] == ["gone", "milk"]
    assert matches["кіноа"].card is None and matches["кіноа"].candidates == []


async def test_match_without_any_available_hit_has_candidates_but_no_card() -> None:
    silpo = FakeSilpo({"молоко": [hit("gone", available=False)]})
    match = (await ProductCatalog(silpo).match(["молоко"]))["молоко"]
    assert match.card is None
    assert len(match.candidates) == 1 and silpo.detail_calls == []


async def test_store_and_slot_are_looked_up_once_per_request() -> None:
    silpo = FakeSilpo({"a": [hit("a1")], "b": [hit("b1")]})
    catalog = ProductCatalog(silpo)
    await catalog.match(["a"])
    await catalog.match(["b"])
    assert silpo.context_calls == 1


async def test_card_fetches_run_in_parallel_but_never_above_the_cap() -> None:
    names = [f"n{i}" for i in range(12)]
    silpo = FakeSilpo({n: [hit(f"p{i}")] for i, n in enumerate(names)}, delay=0.01)
    await ProductCatalog(silpo).match(names)
    assert 1 < silpo.max_running <= CARD_CONCURRENCY
    assert len(silpo.detail_calls) == 12


async def test_one_card_is_fetched_once_even_when_two_ingredients_pick_it() -> None:
    silpo = FakeSilpo({"молоко": [hit("milk")], "milk": [hit("milk")]})
    catalog = ProductCatalog(silpo)
    await catalog.match(["молоко", "milk"])
    await catalog.match(["молоко"])
    assert silpo.detail_calls == ["milk"]


async def test_failed_card_raises_the_original_error_not_a_group() -> None:
    silpo = FakeSilpo({"a": [hit("ok")], "b": [hit("bad")]})
    silpo.broken_slugs.add("bad")
    with pytest.raises(SilpoError):
        await ProductCatalog(silpo).match(["a", "b"])


async def test_similar_returns_candidates() -> None:
    silpo = FakeSilpo({})
    similar = await ProductCatalog(silpo).similar(Candidate.from_search(hit("milk")))
    assert [c.slug for c in similar] == ["alt"]


async def test_candidate_tolerates_a_sparse_search_hit() -> None:
    candidate = Candidate.from_search({"name": "Сир", "slug": "cheese"})
    assert candidate.available is False and candidate.price is None and candidate.stock is None


# ---------- replies of an unexpected shape: read as "nothing", never a crash ----------


class OddSilpo(FakeSilpo):
    """Answers the detail and similar tools with whatever `reply` is."""

    def __init__(self, catalogue: dict[str, list[Any]], reply: Any) -> None:
        super().__init__(catalogue)
        self.reply = reply

    async def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        return self.reply


@pytest.mark.parametrize(
    "reply",
    [
        [{"product": {"url": "https://x", "attributes": {"a": 1}}}],  # a JSON list
        None,
        {"product": ["not", "an", "object"]},
        {"product": {"url": 5, "attributes": "Містить алергени: ЯЙЦЯ"}},
    ],
)
async def test_a_malformed_card_is_an_empty_card(reply: Any) -> None:
    match = (await ProductCatalog(OddSilpo({"a": [hit("a1")]}, reply)).match(["a"]))["a"]
    assert match.card is not None
    assert match.card.url is None and match.card.attributes == {}


async def test_search_hits_that_are_not_objects_are_skipped() -> None:
    silpo = OddSilpo({"a": ["junk", None, hit("a1"), 5]}, {"product": {}})
    match = (await ProductCatalog(silpo).match(["a"]))["a"]
    assert [c.slug for c in match.candidates] == ["a1"]


@pytest.mark.parametrize(
    "reply", [[hit("alt")], None, {"products": None}, {"products": [None, "x"]}]
)
async def test_a_malformed_similar_reply_is_no_alternatives(reply: Any) -> None:
    similar = await ProductCatalog(OddSilpo({}, reply)).similar(Candidate.from_search(hit("milk")))
    assert similar == []
