from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Application settings. Read from environment variables and the .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Shashlychky API"
    version: str = "0.1.0"
    environment: str = "local"
    debug: bool = False
    # Comma-separated list of allowed CORS origins
    cors_origins: str = "http://localhost:5173"

    # Database. Either set DATABASE_URL in full, or the DB_* parts below.
    # DB_HOST is a hostname, or a Cloud SQL unix socket directory such as
    # /cloudsql/<project>:<region>:<instance> (then DB_PORT is ignored).
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "shashlychky"
    db_echo: bool = False

    # LLM (Gemini Developer API). The key lives only on the server: env var / Secret Manager.
    gemini_api_key: str | None = None
    # Cheapest Gemini model available to new API keys (2.5 Flash-Lite is closed to new users).
    gemini_model: str = "gemini-3.1-flash-lite"
    # Used once when the primary model times out or is overloaded (503/504). Empty disables it.
    gemini_fallback_model: str | None = "gemini-3.5-flash-lite"
    # Per-attempt deadline. Flash-Lite answers in 2-6 s; a hung attempt is abandoned and retried.
    llm_timeout_seconds: float = 12.0
    llm_max_output_tokens: int = 2048
    llm_temperature: float = 0.6

    # Silpo MCP server. Empty disables the integration; a localhost URL is the mock (no OAuth).
    silpo_mcp_url: str | None = None

    # Auth. Secure cookies are accepted on http://localhost by Chrome and Firefox, so the
    # default works locally too; set SESSION_COOKIE_SECURE=false only for Safari dev.
    session_cookie_secure: bool = True
    session_ttl_days: int = 30
    # Per-account brute-force guard: after this many wrong passwords the account is locked.
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy URL for the psycopg (v3) driver; works for both sync and async engines."""
        if self.database_url:
            return self.database_url
        if self.db_host.startswith("/"):
            url = URL.create(
                "postgresql+psycopg",
                username=self.db_user,
                password=self.db_password,
                database=self.db_name,
                query={"host": self.db_host},
            )
        else:
            url = URL.create(
                "postgresql+psycopg",
                username=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
            )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
