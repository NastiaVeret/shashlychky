# 4. Typing (High)

`mypy --strict` is on. Types are documentation that is checked.

## Modern syntax only

```python
# Bad
from typing import List, Optional, Dict, Union
def f(xs: List[str], y: Optional[int]) -> Dict[str, Union[int, str]]: ...

# Good
def f(xs: list[str], y: int | None) -> dict[str, int | str]: ...
```

`from __future__ import annotations` is unnecessary on 3.13.

## Accept abstract, return concrete

```python
from collections.abc import Iterable, Mapping, Sequence

def total(prices: Iterable[Decimal]) -> Decimal: ...          # caller may pass a generator
def by_id(orders: Sequence[Order]) -> dict[int, Order]: ...   # caller gets a real dict
```

## `None` is explicit

Return `X | None` only when "nothing" is a legitimate result and the caller must handle it. Otherwise raise. Never return `None` on error "to be safe".

## Avoid `Any`

`Any` turns the checker off. Alternatives in order: a precise type, a `Protocol`, a `TypeVar`, `object` (when you only pass it through), `TypedDict` for JSON you do not own. If `Any` is unavoidable, comment why.

## Type aliases and NewType

```python
type OrderId = int                     # alias: documentation only
UserId = NewType("UserId", int)        # distinct type: mixing UserId and OrderId is a mypy error
```

## Literal and enums

Closed sets of strings: `Literal["draft", "paid"]` for API fields, `enum.StrEnum` when the set needs behaviour or is reused across modules. Not bare `str`.

## Generics

Use 3.12+ syntax: `def first[T](xs: Sequence[T]) -> T: ...`, `class Repo[M: Base]: ...`.

## Narrowing

Prefer `isinstance`, `match`, and `TypeGuard`/`TypeIs` functions over `cast`. `cast` is a last resort with a comment.

## Dependencies without stubs

Add the package to `[[tool.mypy.overrides]]` with `ignore_missing_imports = true` for that one module, never globally.
