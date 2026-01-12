"""User related schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user fields shared across schemas."""

    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    display_name: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None)


class UserCreate(UserBase):
    """Payload for user registration."""

    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Payload for login."""

    username: str
    password: str
    client: str = Field(default="web", pattern=r"^(web|api)$")


class UserPublic(BaseModel):
    """Public safe user fields."""

    id: str
    username: str
    email: EmailStr
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime


class UserInDB(UserPublic):
    """Represents user stored in database."""

    password_hash: str
    wallet_id: str
    roles: list[str]
    status: str


class SessionLoginResponse(BaseModel):
    """Response for session-based login."""

    session_id: str
    csrf_token: str
    expires_at: datetime
    user: UserPublic
