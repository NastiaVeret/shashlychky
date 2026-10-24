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


class LLMUnavailableError(AppError):
    """The model provider timed out, rate-limited us or returned a server error."""

    status_code = 503
    detail = "Сервіс генерації тимчасово недоступний. Спробуйте ще раз за хвилину."


class LLMInvalidResponseError(AppError):
    """The model answered, but not in the expected structure even after a retry."""

    status_code = 502
    detail = "Не вдалося отримати коректний рецепт від моделі. Спробуйте ще раз."
