"""Authentication service for registration, login, refresh, and logout."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from bson import ObjectId
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.db.mongo import MongoClientManager
from app.models.token import TokenPair
from app.models.user import UserCreate, UserLogin, UserPublic
from app.services.users import UserService
from app.services.wallet import WalletService


class AuthService:
    """Coordinates user registration and token lifecycle."""

    def __init__(self, user_service: Optional[UserService] = None, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._client: AsyncIOMotorClient = MongoClientManager.get_client()
        self.user_service = user_service or UserService(db or MongoClientManager.get_database())
        self._db = db or MongoClientManager.get_database()
        self.wallet_service = WalletService(self._db)
        self.refresh_tokens = self._db.get_collection("refresh_tokens")

    async def register_user(self, payload: UserCreate) -> dict[str, Any]:
        async with await self._client.start_session() as session:
            async with session.start_transaction():
                user_id = ObjectId()
                wallet_id = await self.wallet_service.create_wallet(
                    user_id,
                    initial_credits=100,
                    session=session,
                )
                user_doc = await self.user_service.create_user(
                    payload,
                    wallet_id=wallet_id,
                    user_id=user_id,
                    session=session,
                )

        tokens = await self._issue_tokens(user_doc)
        wallet_doc = await self.wallet_service.get_wallet_by_user(str(user_doc["_id"]))
        public = self.user_service.to_public(user_doc)
        return {
            "user": public,
            "wallet": {
                "balance": wallet_doc.get("balance", 0) if wallet_doc else 0,
            },
            "tokens": tokens,
        }

    async def _issue_tokens(self, user_doc: dict[str, Any]) -> TokenPair:
        settings = get_settings()
        user_id = str(user_doc["_id"])
        access_token = create_access_token(
            user_id,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )

        # Create refresh token with JTI for revocation
        jti = str(uuid4())
        refresh_expires = timedelta(minutes=settings.refresh_token_expire_minutes)
        refresh_token = create_refresh_token(
            user_id,
            expires_delta=refresh_expires,
            token_id=jti,
        )

        # Store refresh token in database
        now = datetime.now(timezone.utc)
        await self.refresh_tokens.insert_one(
            {
                "jti": jti,
                "user_id": user_id,
                "created_at": now,
                "expires_at": now + refresh_expires,
                "revoked": False,
            }
        )

        # Create and return TokenPair with user_id
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user_id=user_id
        )

    async def login(self, payload: UserLogin) -> dict[str, Any]:
        user_doc = await self.user_service.authenticate_user(payload)
        tokens = await self._issue_tokens(user_doc)
        public = self.user_service.to_public(user_doc)
        return {"tokens": tokens, "user": public}


    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_refresh_token(refresh_token)
        except ValueError as exc:
            raise AuthenticationError("Invalid refresh token") from exc

        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not jti or not user_id:
            raise AuthenticationError("Invalid refresh token payload")

        token_doc = await self.refresh_tokens.find_one({"jti": jti})
        if not token_doc or token_doc.get("revoked"):
            raise AuthenticationError("Token revoked")

        await self.refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})

        user_doc = await self.user_service.get_user_by_id(user_id)
        if not user_doc:
            raise AuthenticationError("User not found")

        return await self._issue_tokens(user_doc)

    async def logout(self, *, refresh_token: Optional[str], session_id: Optional[str]) -> None:
        if refresh_token:
            try:
                payload = decode_refresh_token(refresh_token)
                jti = payload.get("jti")
                if jti:
                    await self.refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})
            except (ValueError, JWTError):
                pass
