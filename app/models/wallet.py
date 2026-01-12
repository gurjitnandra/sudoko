"""Wallet and transaction response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WalletBalance(BaseModel):
    """Wallet balance response."""

    balance: int = Field(ge=0)


class TransactionEntry(BaseModel):
    """Ledger entry representation."""

    transaction_id: str
    type: str
    amount: int
    game_id: Optional[str] = None
    timestamp: datetime
    status: str
    notes: Optional[str] = None


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    transactions: list[TransactionEntry]
    next_cursor: Optional[str] = None
