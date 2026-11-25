"""Silpo supermarket integration over its MCP server (https://mcp.silpo.ua/mcp).

`connect(url)` yields a `SilpoClient`; a localhost URL talks to the in-memory mock from
`tests/silpo_mock` without OAuth. Notes from the exploration of the real server are in
docs/integrations/silpo.md.
"""

from app.integrations.silpo.client import (
    AddResult,
    NoDeliverySlotsError,
    NoStoreSelectedError,
    SilpoClient,
    SilpoError,
    SilpoNotConnectedError,
    connect,
)

__all__ = [
    "AddResult",
    "NoDeliverySlotsError",
    "NoStoreSelectedError",
    "SilpoClient",
    "SilpoError",
    "SilpoNotConnectedError",
    "connect",
]
