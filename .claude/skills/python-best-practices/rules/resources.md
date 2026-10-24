# 2. Resources, I/O and paths (Critical)

## Context managers for everything that opens

Files, DB sessions, HTTP clients, locks, temp dirs, subprocesses:

```python
# Bad
f = open(path)
data = f.read()

# Good
data = Path(path).read_text(encoding="utf-8")

# Good: several resources
async with httpx.AsyncClient() as http, get_sessionmaker()() as db:
    ...
```

Write your own with `@contextlib.contextmanager` / `@contextlib.asynccontextmanager` instead of try/finally pairs spread across a function.

## `pathlib`, never string paths

```python
# Bad
os.path.join(base, "exports", name + ".csv")

# Good
(Path(base) / "exports" / f"{name}.csv")
path.stem, path.suffix, path.parent, path.exists(), path.mkdir(parents=True, exist_ok=True)
```

Always pass `encoding="utf-8"` to text reads/writes. Binary data uses `read_bytes()` / `write_bytes()`.

## Shared clients live for the process

One `httpx.AsyncClient`, one SQLAlchemy engine, created at startup (FastAPI lifespan) or lazily via a cached factory (`app/db/session.py`), closed at shutdown. Never create a client per request.

## Temporary files

`tempfile.TemporaryDirectory()` / `NamedTemporaryFile()` as context managers. No hand-rolled `/tmp/...` names.

## Subprocesses

`subprocess.run([...], check=True, capture_output=True, text=True, timeout=...)` with a list argv; never `shell=True` with interpolated strings.

## Time

`datetime.now(tz=UTC)` (from `datetime import UTC`), never naive `datetime.now()` or `utcnow()`. Store and compare in UTC; convert at the presentation edge.
