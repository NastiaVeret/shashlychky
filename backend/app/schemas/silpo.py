from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SilpoConnectionRead(BaseModel):
    """Whether the user's own Silpo account is connected. Tokens never leave the server."""

    connected: bool
    connected_at: datetime | None = None


class SilpoAuthorizeRead(BaseModel):
    """Where to send the browser to log in to Silpo; it comes back to /api/v1/silpo/callback."""

    authorize_url: str


class CartItem(BaseModel):
    product_id: str = Field(min_length=1, max_length=64, description="productId товару в Сільпо")
    quantity: float = Field(gt=0, le=100, description="Упаковок, а для вагових товарів кг")


class CartAddRequest(BaseModel):
    """Products from a shopping list to put into the user's own Silpo cart."""

    items: list[CartItem] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def _unique_products(cls, items: list[CartItem]) -> list[CartItem]:
        if len({i.product_id for i in items}) != len(items):
            raise ValueError("Кожен товар можна передати лише один раз")
        return items


class CartAddResult(BaseModel):
    """What is in the cart after adding: Silpo's cart is read back, nothing is assumed."""

    added: list[str] = Field(description="productId, які тепер є в кошику")
    not_added: list[str] = Field(description="productId, яких у кошику немає після додавання")
    notes: list[str] = Field(description="Що варто знати перед оформленням, українською")
    checkout_url: str | None = Field(
        description="Посилання на оформлення в Сільпо; є лише для кошика, який можна оформити"
    )
