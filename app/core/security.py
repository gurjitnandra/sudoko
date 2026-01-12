"""Security utilities for hashing and JWT management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a raw password against the stored hash."""

    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Return a secure hash for a password."""

    return pwd_context.hash(password)


def create_access_token(subject: str, *, expires_delta: Optional[timedelta] = None, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT access token."""

    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, *, expires_delta: Optional[timedelta] = None, token_id: Optional[str] = None) -> str:
    """Create a refresh token with optional token ID."""

    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.refresh_token_expire_minutes))
    payload = {"sub": subject, "exp": expire, "typ": "refresh"}
    if token_id:
        payload["jti"] = token_id
    return jwt.encode(payload, settings.jwt_refresh_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode an access token and return its payload."""

    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # pragma: no cover - handled upstream
        raise ValueError("Invalid access token") from exc


def decode_refresh_token(token: str) -> Dict[str, Any]:
    """Decode a refresh token and return its payload."""

    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_refresh_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # pragma: no cover - handled upstream
        raise ValueError("Invalid refresh token") from exc
