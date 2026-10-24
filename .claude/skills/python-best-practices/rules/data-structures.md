# 5. Data structures (High)

## Pick the container by its job

| Need | Use |
|---|---|
| Internal value object, immutable | `@dataclass(frozen=True, slots=True)` |
| Internal mutable record | `@dataclass(slots=True)` |
| HTTP request/response, config, external JSON | Pydantic `BaseModel` (validation, serialization) |
| Shape of a dict you receive but do not own | `TypedDict` |
| Named tuple semantics (unpacking, tiny) | `NamedTuple` |
| Fixed set of options | `StrEnum` / `Literal` |
| Database row | SQLAlchemy model (`Mapped[...]`) and nothing else |

Do not pass ORM models into Pydantic responses by accident: define a `Read` schema with `model_config = ConfigDict(from_attributes=True)` and convert explicitly.

## Dataclass hygiene

```python
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("amount must be non-negative")
```

Mutable defaults use `field(default_factory=list)`. Equality and ordering come for free; do not hand-write `__eq__`.

## Money and precision

`Decimal` for money and anything that is summed and shown to people; `float` only for measurements. Database columns `Numeric(12, 2)`.

## Prefer the right built-in

- Membership tests on large collections: `set`/`frozenset`, not `list`.
- Counting: `collections.Counter`; grouping: `defaultdict(list)` or `itertools.groupby` on sorted input.
- Ordered unique: `dict.fromkeys(items)`.
- Pairs/zips: `zip(a, b, strict=True)` to catch length mismatches.

## Comprehensions over loops, but readable

One clause, one condition. Nested comprehensions or side effects inside them become a loop.

## Do not mutate inputs

Functions return new values (`sorted(xs)`, `{**d, "k": v}`, `dataclasses.replace(obj, ...)`) instead of mutating the arguments they receive, unless mutation is the documented purpose (`append_item(cart, ...)`).
