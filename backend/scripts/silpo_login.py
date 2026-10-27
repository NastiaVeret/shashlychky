"""Log in to the real Silpo MCP server once (browser OAuth) and save the tokens.

    SILPO_MCP_URL=https://mcp.silpo.ua/mcp uv run python -m scripts.silpo_login

Tokens land in the file storage (backend/.silpo_tokens.json) by default. With --to-db they are
written to the `silpo_tokens` table of the configured database instead, which is what the web
service reads (set DB_* / DATABASE_URL to the target database, e.g. through Cloud SQL Auth Proxy).
"""

import asyncio
import logging
import os
import sys

from app.integrations.silpo import connect

URL = os.environ.get("SILPO_MCP_URL", "https://mcp.silpo.ua/mcp")


async def import_file_to_db() -> None:
    """Copy the tokens of the file storage into the database (no browser needed)."""
    from app.db.session import get_sessionmaker
    from app.integrations.silpo.auth import FileTokenStorage
    from app.integrations.silpo.db_storage import DbTokenStorage

    src, dst = FileTokenStorage(), DbTokenStorage(get_sessionmaker())
    tokens, client_info = await src.get_tokens(), await src.get_client_info()
    if tokens is None:
        raise SystemExit("no tokens in backend/.silpo_tokens.json: run the login first")
    if client_info is not None:
        await dst.set_client_info(client_info)
    await dst.set_tokens(tokens)
    print("Tokens imported into the database (silpo_tokens row 1)")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--import-file" in sys.argv:
        await import_file_to_db()
        return
    to_db = "--to-db" in sys.argv
    storage = None
    if to_db:
        from app.db.session import get_sessionmaker
        from app.integrations.silpo.db_storage import DbTokenStorage

        storage = DbTokenStorage(get_sessionmaker())
    async with connect(URL, storage=storage) as silpo:
        restrictions = await silpo.food_restrictions()
        found = await silpo.find_products(["яйця"], limit=1)
    print("Logged in to Silpo. Food restrictions:", restrictions or "none")
    print("Search works:", bool(found.get("яйця")))
    print("Tokens saved to", "database (silpo_tokens)" if to_db else "backend/.silpo_tokens.json")


if __name__ == "__main__":
    asyncio.run(main())
