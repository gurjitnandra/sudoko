"""Game and participant schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

GameState = Literal["lobby", "in_progress", "finished"]
ParticipantStatus = Literal["joined", "active", "eliminated", "left", "winner"]


class GameCreate(BaseModel):
    buy_in_credit: int = Field(default=10, ge=0)
    rules: dict = Field(default_factory=dict)


class GameJoin(BaseModel):
    game_id: str


class GameScoreUpdate(BaseModel):
    game_id: str
    user_id: str
    delta: int


class ScoreEntry(BaseModel):
    user_id: str
    score: int


class GameFinish(BaseModel):
    game_id: str
    scores: list[ScoreEntry]


class GamePublic(BaseModel):
    id: str
    host_id: str
    buy_in_credit: int
    state: GameState
    participants: list[str]
    pool_amount: int
    created_at: datetime
    updated_at: datetime


class GameResultResponse(BaseModel):
    game_id: str
    winners: list[dict]
    distribution_logic: str
    total_pool: int
    timestamp: datetime
