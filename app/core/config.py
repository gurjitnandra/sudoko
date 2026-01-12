"""Application configuration using Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, BaseSettings, Field


class Settings(BaseSettings):
    """Central application settings.

    The values are loaded from environment variables or a ``.env`` file.
    """

    app_name: str = Field(default="Sudoku Multiplayer Backend")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    backend_cors_origins: List[AnyHttpUrl] | str = Field(default_factory=list)

    mongo_uri: str = Field(default="mongodb://localhost:27017/sudoku")
    mongo_db_name: str = Field(default="sudoku")

    jwt_secret_key: str = Field(default="super-secret-key", min_length=16)
    jwt_refresh_secret_key: str = Field(default="super-refresh-secret-key", min_length=16)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7)

    session_cookie_name: str = Field(default="sudoku_session")
    session_expire_minutes: int = Field(default=60 * 24)

    websocket_heartbeat_interval: int = Field(default=30)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
