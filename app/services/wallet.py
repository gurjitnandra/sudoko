"""Wallet and transaction services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.exceptions import InsufficientCreditsError
from app.db.mongo import MongoClientManager


class WalletService:
    """Encapsulates wallet operations with MongoDB transactions."""

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._client: AsyncIOMotorClient = MongoClientManager.get_client()
        self._db = db if db is not None else MongoClientManager.get_database()
        self.wallets = self._db.get_collection("wallets")
        self.transactions = self._db.get_collection("transactions")

    async def create_wallet(self, user_id: ObjectId, *, initial_credits: int, session=None) -> ObjectId:
        now = datetime.now(timezone.utc)
        wallet_doc = {
            "user_id": user_id,
            "balance": initial_credits,
            "ledger": [],
            "created_at": now,
            "updated_at": now,
        }
        result = await self.wallets.insert_one(wallet_doc, session=session)
        transaction = {
            "transaction_id": str(uuid4()),
            "user_id": user_id,
            "type": "credit",
            "amount": initial_credits,
            "game_id": None,
            "timestamp": now,
            "status": "completed",
            "notes": "initial_credit",
        }
        await self.transactions.insert_one(transaction, session=session)
        return result.inserted_id

    async def get_wallet_by_user(self, user_id: str) -> Optional[dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        return await self.wallets.find_one({"user_id": ObjectId(user_id)})

    async def get_balance(self, user_id: str) -> int:
        wallet = await self.get_wallet_by_user(user_id)
        if not wallet:
            return 0
        return wallet.get("balance", 0)

    async def list_transactions(self, user_id: str, *, limit: int = 20, cursor: Optional[str] = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"user_id": ObjectId(user_id)}
        if cursor:
            query["_id"] = {"$lt": ObjectId(cursor)}
        cursor_obj = self.transactions.find(query).sort("_id", -1).limit(limit)
        return [doc async for doc in cursor_obj]

    async def _apply_ledger_entry(
        self,
        session,
        *,
        wallet_id: ObjectId,
        user_id: ObjectId,
        amount: int,
        entry_type: str,
        game_id: Optional[ObjectId],
        notes: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        transaction_doc = {
            "transaction_id": str(uuid4()),
            "user_id": user_id,
            "type": entry_type,
            "amount": abs(amount),
            "game_id": game_id,
            "timestamp": now,
            "status": "completed",
            "notes": notes,
        }
        await self.transactions.insert_one(transaction_doc, session=session)
        await self.wallets.update_one(
            {"_id": wallet_id},
            {
                "$inc": {"balance": amount},
                "$set": {"updated_at": now},
                "$push": {
                    "ledger": {
                        "amount": amount,
                        "type": entry_type,
                        "game_id": game_id,
                        "timestamp": now,
                        "transaction_id": transaction_doc["transaction_id"],
                        "notes": notes,
                    }
                },
            },
            session=session,
        )

    async def _debit_with_session(
        self,
        session,
        *,
        user_id: ObjectId,
        amount: int,
        game_id: Optional[str],
        notes: str,
    ) -> dict[str, Any]:
        wallet = await self.wallets.find_one({"user_id": user_id}, session=session)
        if not wallet:
            raise InsufficientCreditsError("Wallet not found")
        if wallet.get("balance", 0) < amount:
            raise InsufficientCreditsError("Insufficient credits")
        await self._apply_ledger_entry(
            session,
            wallet_id=wallet["_id"],
            user_id=wallet["user_id"],
            amount=-amount,
            entry_type="debit",
            game_id=ObjectId(game_id) if game_id and ObjectId.is_valid(game_id) else None,
            notes=notes,
        )
        updated = await self.wallets.find_one({"_id": wallet["_id"]}, session=session)
        return updated or wallet

    async def debit(
        self,
        user_id: str,
        *,
        amount: int,
        game_id: Optional[str],
        notes: str,
        session=None,
    ) -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if not ObjectId.is_valid(user_id):
            raise ValueError("Invalid user_id")

        if session is not None:
            return await self._debit_with_session(
                session,
                user_id=ObjectId(user_id),
                amount=amount,
                game_id=game_id,
                notes=notes,
            )

        async with await self._client.start_session() as new_session:
            async with new_session.start_transaction():
                return await self._debit_with_session(
                    new_session,
                    user_id=ObjectId(user_id),
                    amount=amount,
                    game_id=game_id,
                    notes=notes,
                )

    async def _credit_with_session(
        self,
        session,
        *,
        user_id: ObjectId,
        amount: int,
        game_id: Optional[str],
        notes: str,
    ) -> dict[str, Any]:
        wallet = await self.wallets.find_one({"user_id": user_id}, session=session)
        if not wallet:
            raise ValueError("Wallet not found")
        await self._apply_ledger_entry(
            session,
            wallet_id=wallet["_id"],
            user_id=wallet["user_id"],
            amount=amount,
            entry_type="credit",
            game_id=ObjectId(game_id) if game_id and ObjectId.is_valid(game_id) else None,
            notes=notes,
        )
        updated = await self.wallets.find_one({"_id": wallet["_id"]}, session=session)
        return updated or wallet

    async def credit(
        self,
        user_id: str,
        *,
        amount: int,
        game_id: Optional[str],
        notes: str,
        session=None,
    ) -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if not ObjectId.is_valid(user_id):
            raise ValueError("Invalid user_id")

        if session is not None:
            return await self._credit_with_session(
                session,
                user_id=ObjectId(user_id),
                amount=amount,
                game_id=game_id,
                notes=notes,
            )

        async with await self._client.start_session() as new_session:
            async with new_session.start_transaction():
                return await self._credit_with_session(
                    new_session,
                    user_id=ObjectId(user_id),
                    amount=amount,
                    game_id=game_id,
                    notes=notes,
                )
