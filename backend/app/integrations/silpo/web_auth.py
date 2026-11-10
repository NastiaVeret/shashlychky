"""OAuth 2.1 login to Silpo from the web app (authorization code + PKCE, RFC 8707 `resource`).

The MCP SDK runs the whole login inside one coroutine: open the browser, then wait for the
redirect. In a web service the browser leaves and comes back to our callback in a separate
request, so this module does the two halves itself: `start_authorization` (discovery, dynamic
client registration, authorize URL) and `exchange_code`. The tokens and client registration go
into a `DbTokenStorage`; from there the SDK uses and refreshes them as usual.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import httpx
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from pydantic import ValidationError

from app.integrations.silpo.auth import SilpoAuthError, client_metadata


@dataclass(frozen=True, slots=True)
class PendingAuthorization:
    authorize_url: str
    state: str
    code_verifier: str
    client_info: OAuthClientInformationFull


async def discover(server_url: str, http: httpx.AsyncClient) -> OAuthMetadata:
    """Authorization server metadata: protected resource metadata (RFC 9728), then RFC 8414."""
    parsed = urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    issuer = origin
    # Path-specific URL first, as the MCP spec says; Silpo answers only the root one.
    for url in (
        f"{origin}/.well-known/oauth-protected-resource{parsed.path}",
        f"{origin}/.well-known/oauth-protected-resource",
    ):
        response = await http.get(url)
        if response.status_code != 200:
            continue
        try:
            resource = ProtectedResourceMetadata.model_validate_json(response.content)
        except ValidationError:
            continue
        issuer = str(resource.authorization_servers[0])
        break
    response = await http.get(f"{issuer.rstrip('/')}/.well-known/oauth-authorization-server")
    response.raise_for_status()
    return OAuthMetadata.model_validate_json(response.content)


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)  # 86 characters, within RFC 7636's 43-128
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def start_authorization(
    server_url: str,
    redirect_uri: str,
    http: httpx.AsyncClient,
    client_info: OAuthClientInformationFull | None = None,
) -> PendingAuthorization:
    """Where to send the browser. Registers a client unless `client_info` is still usable."""
    meta = await discover(server_url, http)
    registered_for = [str(u) for u in (client_info.redirect_uris or [])] if client_info else []
    if client_info is None or redirect_uri not in registered_for:
        if meta.registration_endpoint is None:
            raise SilpoAuthError("Silpo does not offer dynamic client registration")
        response = await http.post(
            str(meta.registration_endpoint),
            json=client_metadata(redirect_uri).model_dump(mode="json", exclude_none=True),
        )
        response.raise_for_status()
        client_info = OAuthClientInformationFull.model_validate_json(response.content)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": client_info.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": server_url,
    }
    return PendingAuthorization(
        authorize_url=f"{meta.authorization_endpoint}?{urlencode(params)}",
        state=state,
        code_verifier=verifier,
        client_info=client_info,
    )


async def exchange_code(
    server_url: str,
    redirect_uri: str,
    client_info: OAuthClientInformationFull,
    code: str,
    code_verifier: str,
    http: httpx.AsyncClient,
) -> OAuthToken:
    meta = await discover(server_url, http)
    response = await http.post(
        str(meta.token_endpoint),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_info.client_id or "",
            "code_verifier": code_verifier,
            "resource": server_url,
        },
    )
    response.raise_for_status()
    return OAuthToken.model_validate_json(response.content)
