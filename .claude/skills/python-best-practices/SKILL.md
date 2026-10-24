---
name: python-best-practices
description: Modern Python 3.13 standards for this backend - typing, data structures, error handling, resources, async, FastAPI and SQLAlchemy idioms, naming, docstrings, tests. Use when writing, reviewing or refactoring any Python code in backend/, when choosing between dataclass/pydantic/TypedDict, when handling errors or resources, or when asked "is this idiomatic", "clean this up", "review the Python".
---

# Python best practices (backend)

Adapted from PEP 8, the Google Python Style Guide and the cuioss `python-best-practices` skill,
narrowed to what this project uses: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 async, pytest, ruff, mypy --strict.
Formatting is ruff's job; this skill is about design and idioms.

## How to use

1. While writing: skim the quick reference below, open the matching `rules/*.md` when unsure.
2. While reviewing: walk the categories in order; the first three are where real bugs live.
3. Conflicts: project rules in `.claude/rules/*.md` win over this skill; this skill wins over habit.

## Quick reference

| # | Category | Priority | File |
|---|---|---|---|
| 1 | Errors and exceptions | Critical | `rules/errors.md` |
| 2 | Resources, I/O and paths | Critical | `rules/resources.md` |
| 3 | Async correctness | Critical | `rules/async.md` |
| 4 | Typing | High | `rules/typing.md` |
| 5 | Data structures | High | `rules/data-structures.md` |
| 6 | FastAPI and SQLAlchemy idioms | High | `rules/fastapi-sqlalchemy.md` |
| 7 | Functions, modules, naming, docstrings | Medium | `rules/structure.md` |
| 8 | Tests | Medium | `rules/testing.md` |

### The ten rules worth memorizing

1. Catch the narrowest exception that you can handle; never bare `except:` or silent `except Exception: pass`.
2. Re-raise with context: `raise AppError(...) from exc`.
3. Every file, socket, session, lock goes through `with` / `async with`.
4. No blocking I/O in `async def` (no `requests`, `time.sleep`, sync DB drivers, `open()` on big files).
5. Independent awaits run concurrently with `asyncio.gather` / `TaskGroup`, not one after another.
6. Built-in generics and `X | None`; parameters typed with `collections.abc` protocols (`Sequence`, `Mapping`, `Iterable`), returns typed concretely.
7. `dataclass(frozen=True, slots=True)` for internal values, Pydantic only at boundaries (HTTP, config, external JSON), `TypedDict` for untyped dict shapes you do not own.
8. Functions do one thing, take at most ~5 parameters, return early, and never mutate their arguments unless that is their stated purpose.
9. Names say what, not how: `pending_orders`, not `lst`; `is_`/`has_` for booleans; `_private` for module internals.
10. Docstrings explain why and the contract (Args/Returns/Raises) for anything public or non-obvious; no docstring that repeats the signature.
