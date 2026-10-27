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


class SessionExpiredError(NotAuthenticatedError):
    """A session cookie was sent but it is expired, revoked or forged. The handler clears it."""

    detail = "Сесія закінчилася, увійдіть знову"


class InvalidCredentialsError(NotAuthenticatedError):
    """Wrong email or password. One message for both, so emails cannot be probed via login."""

    detail = "Невірний email або пароль"


class TooManyLoginAttemptsError(AppError):
    status_code = 429
    detail = "Забагато невдалих спроб входу. Спробуйте пізніше."


class AllergenInProductsError(AppError):
    """The user listed a product that is one of their own allergens."""

    status_code = 422
    detail = "Серед продуктів є ваш алерген. Приберіть його або оновіть профіль."


class LLMUnavailableError(AppError):
    """The model provider timed out, rate-limited us or returned a server error."""

    status_code = 503
    detail = "Сервіс генерації тимчасово недоступний. Спробуйте ще раз за хвилину."


class NutritionUnavailableError(AppError):
    """The product catalogue (Silpo) is not configured or did not answer."""

    status_code = 503
    detail = "Дані про КБЖВ з Сільпо тимчасово недоступні. Спробуйте пізніше."


class LLMInvalidResponseError(AppError):
    """The model answered, but not in the expected structure even after a retry."""

    status_code = 502
    detail = "Не вдалося отримати коректний рецепт від моделі. Спробуйте ще раз."


class AllergenInRecipeError(LLMInvalidResponseError):
    """The model kept putting one of the user's allergens into the recipe, even after a retry."""

    detail = "Не вдалося підібрати рецепт без ваших алергенів. Спробуйте інші продукти."
