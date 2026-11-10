"""The web OAuth flow against a fake Silpo authorization server (httpx.MockTransport)."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from mcp.shared.auth import OAuthClientInformationFull

from app.integrations.silpo.auth import SilpoAuthError
from app.integrations.silpo.web_auth import exchange_code, start_authorization

SERVER = "https://mcp.example.test/mcp"
ISSUER = "https://mcp.example.test"
REDIRECT = "https://app.example.test/api/v1/silpo/callback"
TOKENS = {"access_token": "A", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "R"}


class FakeSilpo:
    """Answers like mcp.silpo.ua: no path-specific resource metadata, DCR, a token endpoint."""

    def __init__(self) -> None:
        self.registrations = 0
        self.token_requests: list[dict[str, list[str]]] = []
        self.fail_registration = False
        self.fail_token = False
        self.offer_registration = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/.well-known/oauth-protected-resource":
                return httpx.Response(
                    200, json={"resource": SERVER, "authorization_servers": [ISSUER]}
                )
            case "/.well-known/oauth-authorization-server":
                meta = {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "response_types_supported": ["code"],
                }
                if self.offer_registration:
                    meta["registration_endpoint"] = f"{ISSUER}/register"
                return httpx.Response(200, json=meta)
            case "/register":
                if self.fail_registration:
                    return httpx.Response(500)
                self.registrations += 1
                body = json.loads(request.content)
                return httpx.Response(
                    201, json={**body, "client_id": f"client-{self.registrations}"}
                )
            case "/token":
                self.token_requests.append(parse_qs(request.content.decode()))
                if self.fail_token:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json=TOKENS)
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def challenge_of(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def test_start_registers_client_and_builds_pkce_url() -> None:
    silpo = FakeSilpo()
    async with silpo.client() as http:
        pending = await start_authorization(SERVER, REDIRECT, http)

    url = urlparse(pending.authorize_url)
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == f"{ISSUER}/authorize"
    assert params == {
        "response_type": "code",
        "client_id": "client-1",
        "redirect_uri": REDIRECT,
        "state": pending.state,
        "code_challenge": challenge_of(pending.code_verifier),
        "code_challenge_method": "S256",
        "resource": SERVER,
    }
    assert silpo.registrations == 1
    assert pending.client_info.client_id == "client-1"


async def test_start_reuses_registration_for_same_redirect_uri() -> None:
    silpo = FakeSilpo()
    known = OAuthClientInformationFull(client_id="old", redirect_uris=[REDIRECT])  # type: ignore[list-item]
    async with silpo.client() as http:
        same = await start_authorization(SERVER, REDIRECT, http, known)
        other = await start_authorization(SERVER, "http://localhost:5173/cb", http, known)

    assert same.client_info.client_id == "old"
    assert other.client_info.client_id == "client-1"
    assert silpo.registrations == 1


async def test_start_without_registration_endpoint_fails() -> None:
    silpo = FakeSilpo()
    silpo.offer_registration = False
    async with silpo.client() as http:
        with pytest.raises(SilpoAuthError):
            await start_authorization(SERVER, REDIRECT, http)


async def test_exchange_code_sends_verifier_and_returns_tokens() -> None:
    silpo = FakeSilpo()
    client = OAuthClientInformationFull(client_id="cid", redirect_uris=[REDIRECT])  # type: ignore[list-item]
    async with silpo.client() as http:
        tokens = await exchange_code(SERVER, REDIRECT, client, "the-code", "the-verifier", http)

    assert tokens.access_token == "A" and tokens.refresh_token == "R"
    (sent,) = silpo.token_requests
    assert sent["code"] == ["the-code"]
    assert sent["code_verifier"] == ["the-verifier"]
    assert sent["client_id"] == ["cid"]
    assert sent["redirect_uri"] == [REDIRECT]
    assert sent["resource"] == [SERVER]


async def test_exchange_code_rejected_raises_http_error() -> None:
    silpo = FakeSilpo()
    silpo.fail_token = True
    client = OAuthClientInformationFull(client_id="cid", redirect_uris=[REDIRECT])  # type: ignore[list-item]
    async with silpo.client() as http:
        with pytest.raises(httpx.HTTPStatusError):
            await exchange_code(SERVER, REDIRECT, client, "c", "v", http)
