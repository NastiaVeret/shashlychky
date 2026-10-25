"""Application error hierarchy. Services raise these; the API layer maps them to HTTP responses."""


class AppError(Exception):
    """Base class for expected application errors."""

    status_code = 500
    detail = "Внутрішня помилка"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail


class NotFoundError(AppError):
    status_code = 404
    detail = "Не знайдено"


class ConflictError(AppError):
    status_code = 409
    detail = "Конфлікт даних"


class NotAuthenticatedError(AppError):
    """No session cookie, or the session expired or was revoked."""

    status_code = 401
    detail = "Потрібно увійти"


class InvalidCredentialsError(NotAuthenticatedError):
    """Wrong email or password. One message for both, so emails cannot be probed via login."""

    detail = "Невірний email або пароль"


class TooManyLoginAttemptsError(AppError):
    status_code = 429
    detail = "Забагато невдалих спроб входу. Спробуйте пізніше."


class LLMUnavailableError(AppError):
    """The model provider timed out, rate-limited us or returned a server error."""

    status_code = 503
    detail = "Сервіс генерації тимчасово недоступний. Спробуйте ще раз за хвилину."


class LLMInvalidResponseError(AppError):
    """The model answered, but not in the expected structure even after a retry."""

    status_code = 502
    detail = "Не вдалося отримати коректний рецепт від моделі. Спробуйте ще раз."
