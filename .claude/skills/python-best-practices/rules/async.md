# 3. Async correctness (Critical)

The whole backend runs on one event loop per worker. One blocking call stalls every request in flight.

## No blocking calls in `async def`

| Blocking | Async replacement |
|---|---|
| `requests.get` | `httpx.AsyncClient` |
| `time.sleep` | `await asyncio.sleep` |
| sync SQLAlchemy `Session` | `AsyncSession` (`app/db/session.py`) |
| `open().read()` on large files, CPU-heavy work | `await asyncio.to_thread(fn, ...)` |

## Independent work runs concurrently

```python
# Bad: sequential waterfall, latency adds up
user = await get_user(uid)
orders = await get_orders(uid)
prefs = await get_prefs(uid)

# Good
user, orders, prefs = await asyncio.gather(get_user(uid), get_orders(uid), get_prefs(uid))
```

Use `asyncio.TaskGroup` when tasks should be cancelled together on the first failure. Note: one `AsyncSession` is not safe for concurrent use; gather only queries that use different sessions, or run them sequentially within one session.

## Bound concurrency

Fan-out to an external API goes through `asyncio.Semaphore(n)`; unbounded `gather` over a thousand items is a self-inflicted DoS.

## Timeouts everywhere

`async with asyncio.timeout(5):` around external calls; `httpx.AsyncClient(timeout=...)` always set. A missing timeout is a hung request waiting to happen.

## Cancellation

Do not catch `asyncio.CancelledError` unless you re-raise it. `except Exception` does not catch it (it is a `BaseException`), which is the right default.

## Fire-and-forget is a leak

`asyncio.create_task(...)` without keeping the reference may be garbage-collected mid-flight and its exceptions are lost. Store tasks in a set or use FastAPI `BackgroundTasks` for post-response work.

## Entry points

Scripts: `asyncio.run(main())`. Tests: `pytest-asyncio` in auto mode (already configured); fixtures that need the loop are `async def`.
