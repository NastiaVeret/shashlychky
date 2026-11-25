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
    # Tried in order when the primary times out, is overloaded (429/5xx) or does not exist (404).
    # Separated by spaces or commas (Cloud Run deploy splits env vars on commas: use spaces there).
    # Empty disables fallback.
    # Deliberately long: each model has its own free-tier quota and overload state, and a name
    # the API does not know costs ~0.2 s once (404), then is skipped for an hour.
    gemini_fallback_models: str = (
        "gemini-3.5-flash-lite gemini-flash-lite-latest gemini-3.8-flash-lite "
        "gemini-3.1-flash-lite-preview gemini-3.8-flash gemini-flash-latest "
        "gemini-3.5-flash gemini-3.1-flash gemini-3-flash gemini-3-flash-preview"
    )
    # Per-attempt deadline. Flash-Lite answers in 2-6 s; a hung attempt is abandoned for the next.
    llm_timeout_seconds: float = 15.0
    # Budget for the whole generation incl. fallbacks and retries. Firebase Hosting cuts proxied
    # requests at 60 s, so stay under it to answer with a clean 503 instead of a gateway error.
    llm_total_timeout_seconds: float = 50.0
    # Passes over the model chain before giving up (a short pause between passes).
    llm_retry_rounds: int = 3
    llm_max_output_tokens: int = 2048
    llm_temperature: float = 0.6

    # Silpo MCP server. Empty disables the integration; a localhost URL is the mock (no OAuth).
    silpo_mcp_url: str | None = None
    # Public origin of the web app, for the Silpo OAuth redirect URI. Empty: the first CORS
    # origin, which is the frontend in every environment (Firebase Hosting proxies /api).
    public_url: str | None = None

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
    def silpo_redirect_uri(self) -> str:
        origin = (self.public_url or self.cors_origin_list[0]).rstrip("/")
        return f"{origin}/api/v1/silpo/callback"

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
