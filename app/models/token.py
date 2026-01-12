"""Token related schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TokenPair(BaseModel):
    """Represents an access/refresh token pair with user information."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str


class RefreshTokenPayload(BaseModel):
    """Payload for refresh requests."""

    refresh_token: str


class LogoutPayload(BaseModel):
    """Payload for logout requests."""

    refresh_token: Optional[str] = None
    session_id: Optional[str] = None


class TokenMetadata(BaseModel):
    """Metadata stored for issued refresh tokens."""

    jti: str
    user_id: str
    created_at: datetime
    expires_at: datetime
