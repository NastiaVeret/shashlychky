# 1. Errors and exceptions (Critical)

## Catch narrowly, keep `try` small

```python
# Bad: hides every bug in the block, including typos
try:
    order = parse(payload)
    total = price_for(order)
    save(order, total)
except Exception:
    return None

# Good: one risky call, one expected failure
try:
    order = parse(payload)
except ValidationError as exc:
    raise HTTPException(status_code=422, detail=str(exc)) from exc
total = price_for(order)
save(order, total)
```

## Chain exceptions

`raise ... from exc` keeps the original traceback; `raise ... from None` deliberately hides it (rare, comment why).

## Never swallow

`except Exception: pass` and `except Exception: logger.error(...)` without re-raising are bugs unless the function's contract is "best effort" and that is written in the docstring. Even then, log with `logger.exception(...)` so the traceback is kept.

## Domain exceptions

One small hierarchy per bounded context, rooted in a project base class:

```python
class AppError(Exception):
    """Base class for expected application errors."""

class NotFoundError(AppError): ...
class ConflictError(AppError): ...
```

Services raise domain errors; the API layer maps them to HTTP codes in one place (an exception handler in `main.py`), not in every router.

## Validate at the boundary, trust inside

Pydantic validates HTTP input and config once. Internal functions take already-valid typed values and do not re-check them; they use `assert` only for programmer errors, never for input validation (asserts are stripped with `-O`).

## Exceptions are for exceptional flow

Expected "not found" from a query returns `None` (`await db.get(Order, id)` already does); the service turns `None` into `NotFoundError` where that is the contract. Do not use exceptions to return values or to break loops.

## Errors in logs

`logger.exception("...")` inside an `except` block; include identifiers (`order_id=%s`), never secrets or whole request bodies.
