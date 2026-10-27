import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_PASSWORD_LEN = 8
# Argon2 handles any length; the cap only bounds request size and hashing time.
MAX_PASSWORD_LEN = 128
# Deliberately loose: the real check would be a confirmation email, which v1 does not send.
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class LoginRequest(BaseModel):
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_LEN)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        """Trim and lowercase, so `User@Mail.com ` and `user@mail.com` are one account."""
        email = email.strip().lower()
        if not EMAIL_RE.fullmatch(email):
            raise ValueError("Некоректна email-адреса")
        return email


class RegisterRequest(LoginRequest):
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LEN, max_length=MAX_PASSWORD_LEN)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime
