"""Pydantic models for authentication and session management."""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class Token(BaseModel):
    """JWT token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str

class TokenData(BaseModel):
    """Token data model."""
    username: Optional[str] = None
    user_id: Optional[str] = None

class UserLogin(BaseModel):
    """User login model."""
    username: str
    password: str

class UserRegister(BaseModel):
    """User registration model."""
    username: str
    email: EmailStr
    password: str
    display_name: Optional[str] = None

class SessionRefresh(BaseModel):
    """Session refresh request model."""
    session_id: Optional[str] = None  # Will be taken from cookie if not provided

class RefreshTokenPayload(BaseModel):
    """Refresh token payload model."""
    refresh_token: str


class SessionResponse(BaseModel):
    """Session response model."""
    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    is_active: bool

class UserResponse(BaseModel):
    """User response model (public)."""
    id: str
    username: str
    email: str
    display_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

class PasswordResetRequest(BaseModel):
    """Password reset request model."""
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    """Password reset confirmation model."""
    token: str
    new_password: str
