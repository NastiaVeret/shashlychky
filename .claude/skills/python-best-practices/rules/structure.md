# 7. Functions, modules, naming, docstrings (Medium)

## Functions

- One job, named with a verb: `calculate_total`, `load_orders`, `is_expired`.
- Up to ~5 parameters; more means a dataclass or that the function does too much.
- Keyword-only for booleans and optional knobs: `def export(orders, *, include_cancelled=False)`.
- Return early for guards; the happy path is the least indented code.
- No hidden side effects: a function that reads should not also write.

## Modules

- Module = one topic. `services/orders.py`, not `utils.py` (a `utils` module is where unrelated things go to hide).
- Imports at the top, absolute, grouped stdlib / third-party / first-party (ruff enforces).
- No work at import time except constants and definitions. Engines, clients and settings are created lazily or in lifespan.
- `__all__` only in packages that are public APIs.

## Naming

| Thing | Style | Example |
|---|---|---|
| modules, functions, variables | `lower_with_under` | `order_service`, `pending_orders` |
| classes, exceptions | `CapWords` | `OrderRead`, `NotFoundError` |
| constants | `CAPS_WITH_UNDER` | `MAX_PAGE_SIZE` |
| internal | leading underscore | `_normalize` |
| booleans | `is_`, `has_`, `can_` | `is_paid` |
| collections | plural | `orders`, `ids_by_user` |

Avoid abbreviations that are not universal (`cfg`, `usr`, `tmp_lst`). `id`, `db`, `url` are fine.

## Docstrings (Google style)

Public functions, classes, modules and anything non-obvious. State the contract, not the implementation.

```python
def reserve(db: AsyncSession, order_id: int, *, quantity: int) -> Reservation:
    """Reserve stock for an order.

    Args:
        db: Active session; the caller commits.
        order_id: Order to reserve for.
        quantity: Units to reserve, must be positive.

    Returns:
        The created reservation.

    Raises:
        NotFoundError: If the order does not exist.
        ConflictError: If stock is insufficient.
    """
```

No docstring that only restates the name (`"""Gets the order."""`). Comments explain *why*; code explains *what*.

## Pattern matching

`match` for destructuring tagged unions and nested data; not as a replacement for a simple `if/elif` on one value.

## Zen, applied

Readability counts. Explicit beats implicit. Errors never pass silently. Flat beats nested. If the implementation is hard to explain, it is a bad idea.
