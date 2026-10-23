"""OAuth 2.1 (PKCE + динамічна реєстрація клієнта) для реального MCP Сільпо.

Готово для локальної розробки та скриптів: відкриває браузер, ловить редірект
на http://localhost:8765/callback і зберігає токени у файлі. Для вебсервісу
реалізуйте ті самі два обробники (redirect_handler, callback_handler) і
TokenStorage на користувача (БД), решта коду не змінюється.
Токени ніколи не віддавати у фронтенд.
"""
import asyncio
import json
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
DEFAULT_TOKEN_FILE = Path(".silpo_tokens.json")  # у .gitignore


class FileTokenStorage(TokenStorage):
    """Токени й дані зареєстрованого клієнта в JSON-файлі."""

    def __init__(self, path: Path = DEFAULT_TOKEN_FILE):
        self.path = path

    def _read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _write(self, key: str, value) -> None:
        data = self._read()
        data[key] = value.model_dump(mode="json", exclude_none=True)
        self.path.write_text(json.dumps(data))
        self.path.chmod(0o600)

    async def get_tokens(self) -> OAuthToken | None:
        d = self._read().get("tokens")
        return OAuthToken(**d) if d else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens", tokens)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        d = self._read().get("client_info")
        return OAuthClientInformationFull(**d) if d else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write("client_info", client_info)


async def open_in_browser(url: str) -> None:
    print(f"Відкрийте для входу в Сільпо (якщо браузер не відкрився сам):\n{url}")
    webbrowser.open(url)


async def wait_for_callback() -> tuple[str, str | None]:
    """Піднімає одноразовий localhost-сервер і чекає редірект із code та state."""
    result: asyncio.Future[tuple[str, str | None]] = asyncio.get_running_loop().create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode()
        query = parse_qs(urlparse(request_line.split(" ")[1]).query)
        body = "Готово, можна закрити вкладку.".encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
                     b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        if "code" in query and not result.done():
            result.set_result((query["code"][0], query.get("state", [None])[0]))
        elif "error" in query and not result.done():
            result.set_exception(RuntimeError(f"Авторизація відхилена: {query['error'][0]}"))

    server = await asyncio.start_server(handle, "127.0.0.1", REDIRECT_PORT)
    try:
        return await asyncio.wait_for(result, timeout=300)
    finally:
        server.close()


def make_auth(server_url: str, storage: TokenStorage | None = None,
              redirect_handler=open_in_browser, callback_handler=wait_for_callback) -> OAuthClientProvider:
    """Провайдер авторизації для streamablehttp_client(url, auth=...)."""
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=OAuthClientMetadata(
            client_name="Cook 'n' Love",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage or FileTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
