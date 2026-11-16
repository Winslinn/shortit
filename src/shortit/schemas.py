import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator

class Link(BaseModel):
    id: str
    url: HttpUrl
    user_id: int | None = None
    clicks: int = 0

    model_config = ConfigDict(from_attributes=True)

class Links(BaseModel):
    links: list[Link]

class LinkCreate(BaseModel):
    url: HttpUrl
    turnstile_token: str | None = None

class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        normalized = email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, password: SecretStr) -> SecretStr:
        if len(password.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return password

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        normalized = email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, password: SecretStr) -> SecretStr:
        if len(password.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return password


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)

class UserRead(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserRead
