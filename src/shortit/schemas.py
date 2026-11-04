from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, SecretStr

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
    email: str
    password: SecretStr

class LoginRequest(BaseModel):
    email: str
    password: SecretStr


class UserRead(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
