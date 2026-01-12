"""User service encapsulating MongoDB operations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import hash_password, verify_password
from app.models.user import UserCreate, UserLogin, UserPublic
from app.models.db import PyObjectId
from app.core.exceptions import AuthenticationError, ConflictError
from app.db.mongo import MongoClientManager


class UserService:
    """Service for user CRUD and authentication related operations."""

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db if db is not None else MongoClientManager.get_database()
        self.users = self._db.get_collection("users")

    async def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        return await self.users.find_one({"_id": ObjectId(user_id)})

    async def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        return await self.users.find_one({"username": username})

    async def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        return await self.users.find_one({"email": email})

    async def create_user(
        self,
        payload: UserCreate,
        *,
        wallet_id: ObjectId,
        user_id: Optional[ObjectId] = None,
        session=None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        profile = {
            "display_name": payload.display_name or payload.username,
        }
        
        # Only add avatar_url if it exists in the payload
        if hasattr(payload, 'avatar_url') and payload.avatar_url is not None:
            profile["avatar_url"] = payload.avatar_url
            
        doc = {
            "_id": user_id or ObjectId(),
            "username": payload.username,
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "profile": profile,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "roles": ["user"],
            "wallet_id": wallet_id,
        }
        try:
            await self.users.insert_one(doc, session=session)
        except Exception as exc:  # pragma: no cover - captured analytics
            if "duplicate" in str(exc).lower():
                raise ConflictError("Username or email already exists") from exc
            raise
        return doc

    async def authenticate_user(self, payload: UserLogin) -> dict[str, Any]:
        user = await self.get_user_by_username(payload.username)
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise AuthenticationError("Invalid credentials")
        if user.get("status") != "active":
            raise AuthenticationError("Account disabled")
        return user

    @staticmethod
    def to_public(user_doc: dict[str, Any]) -> UserPublic:
        return UserPublic(
            id=str(user_doc["_id"]),
            username=user_doc["username"],
            email=user_doc["email"],
            display_name=user_doc.get("profile", {}).get("display_name"),
            avatar_url=user_doc.get("profile", {}).get("avatar_url"),
            created_at=user_doc.get("created_at"),
        )
