"""Shared Pydantic models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Simple message payload."""

    success: bool = True
    message: str = Field(default="")


class PaginationParams(BaseModel):
    """Query params for pagination."""

    limit: int = Field(default=20, ge=1, le=100)
    cursor: Optional[str] = None


class TransactionRef(BaseModel):
    """Reference to a transaction entry."""

    transaction_id: str
    timestamp: datetime
