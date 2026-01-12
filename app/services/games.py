"""Game service managing lobby, scoring, and credit distribution."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, InsufficientCreditsError
from app.db.mongo import MongoClientManager
from app.models.game import GameFinish
from app.services.wallet import WalletService


class GameService:
    """Encapsulates MongoDB operations related to multiplayer games."""

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._client: AsyncIOMotorClient = MongoClientManager.get_client()
        self._db = db or MongoClientManager.get_database()
        self.games = self._db.get_collection("games")
        self.participants = self._db.get_collection("game_participants")
        self.results = self._db.get_collection("game_results")
        self.wallet_service = WalletService(self._db)

    async def _get_game(self, game_id: str, *, session=None) -> dict[str, Any]:
        if not ObjectId.is_valid(game_id):
            raise ConflictError("Invalid game id")
        game = await self.games.find_one({"_id": ObjectId(game_id)}, session=session)
        if not game:
            raise ConflictError("Game not found")
        return game

    async def create_game(self, host_id: str, buy_in: int, rules: dict) -> dict[str, Any]:
        if buy_in < 0:
            raise ValueError("buy_in must be positive")
        if not ObjectId.is_valid(host_id):
            raise ValueError("Invalid host id")

        async with await self._client.start_session() as session:
            async with session.start_transaction():
                await self.wallet_service.debit(
                    host_id,
                    amount=buy_in,
                    game_id=None,
                    notes="host_game_fee",
                    session=session,
                )
                now = datetime.now(timezone.utc)
                game_doc = {
                    "host_id": ObjectId(host_id),
                    "buy_in_credit": buy_in,
                    "state": "lobby",
                    "rules": rules or {},
                    "participants": [ObjectId(host_id)],
                    "pool_amount": buy_in,
                    "created_at": now,
                    "updated_at": now,
                    "result_id": None,
                }
                result = await self.games.insert_one(game_doc, session=session)
                await self.participants.insert_one(
                    {
                        "game_id": result.inserted_id,
                        "user_id": ObjectId(host_id),
                        "joined_at": now,
                        "score": 0,
                        "status": "joined",
                        "ws_status": "offline",
                        "last_seen": now,
                    },
                    session=session,
                )
                game_doc["_id"] = result.inserted_id
                return game_doc

    async def join_game(self, game_id: str, user_id: str, buy_in: Optional[int] = None) -> dict[str, Any]:
        if not ObjectId.is_valid(user_id):
            raise ValueError("Invalid user id")
        async with await self._client.start_session() as session:
            async with session.start_transaction():
                game = await self._get_game(game_id, session=session)
                if game["state"] != "lobby":
                    raise ConflictError("Game already started")
                if ObjectId(user_id) in game["participants"]:
                    raise ConflictError("Already joined")
                buy_in_credit = buy_in if buy_in is not None else game.get("buy_in_credit", 10)
                await self.wallet_service.debit(
                    user_id,
                    amount=buy_in_credit,
                    game_id=game_id,
                    notes="join_game_fee",
                    session=session,
                )
                now = datetime.now(timezone.utc)
                await self.games.update_one(
                    {"_id": game["_id"]},
                    {
                        "$push": {"participants": ObjectId(user_id)},
                        "$inc": {"pool_amount": buy_in_credit},
                        "$set": {"updated_at": now},
                    },
                    session=session,
                )
                await self.participants.insert_one(
                    {
                        "game_id": game["_id"],
                        "user_id": ObjectId(user_id),
                        "joined_at": now,
                        "score": 0,
                        "status": "joined",
                        "ws_status": "offline",
                        "last_seen": now,
                    },
                    session=session,
                )
                game["participants"].append(ObjectId(user_id))
                game["pool_amount"] += buy_in_credit
                return game

    async def start_game(self, game_id: str, host_id: str) -> dict[str, Any]:
        async with await self._client.start_session() as session:
            async with session.start_transaction():
                game = await self._get_game(game_id, session=session)
                if str(game["host_id"]) != host_id:
                    raise ConflictError("Only host can start")
                if game["state"] != "lobby":
                    raise ConflictError("Game already started")
                now = datetime.now(timezone.utc)
                await self.games.update_one(
                    {"_id": game["_id"]},
                    {"$set": {"state": "in_progress", "updated_at": now}},
                    session=session,
                )
                game["state"] = "in_progress"
                return game

    async def update_score(self, game_id: str, user_id: str, delta: int) -> dict[str, Any]:
        async with await self._client.start_session() as session:
            async with session.start_transaction():
                participant = await self.participants.find_one(
                    {"game_id": ObjectId(game_id), "user_id": ObjectId(user_id)},
                    session=session,
                )
                if not participant:
                    raise ConflictError("Participant not found")
                await self.participants.update_one(
                    {"_id": participant["_id"]},
                    {"$inc": {"score": delta}, "$set": {"status": "active", "last_seen": datetime.now(timezone.utc)}},
                    session=session,
                )
                participant["score"] += delta
                return participant

    async def set_participant_ws_status(self, game_id: str, user_id: str, status: str) -> None:
        if not (ObjectId.is_valid(game_id) and ObjectId.is_valid(user_id)):
            return
        await self.participants.update_one(
            {"game_id": ObjectId(game_id), "user_id": ObjectId(user_id)},
            {
                "$set": {
                    "ws_status": status,
                    "last_seen": datetime.now(timezone.utc),
                }
            },
        )

    async def list_active_games_for_user(self, user_id: str) -> list[dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return []
        cursor = self.participants.aggregate(
            [
                {"$match": {"user_id": ObjectId(user_id)}},
                {
                    "$lookup": {
                        "from": "games",
                        "localField": "game_id",
                        "foreignField": "_id",
                        "as": "game",
                    }
                },
                {"$unwind": "$game"},
                {"$replaceRoot": {"newRoot": "$game"}},
            ]
        )
        return [doc async for doc in cursor]

    async def list_participants(self, game_id: str) -> list[dict[str, Any]]:
        if not ObjectId.is_valid(game_id):
            return []
        cursor = self.participants.find({"game_id": ObjectId(game_id)})
        return [doc async for doc in cursor]

    async def finish_game(self, payload: GameFinish, host_id: str) -> dict[str, Any]:
        async with await self._client.start_session() as session:
            async with session.start_transaction():
                game = await self._get_game(payload.game_id, session=session)
                if str(game["host_id"]) != host_id:
                    raise ConflictError("Only host can finish")
                if game["state"] != "in_progress":
                    raise ConflictError("Game not in progress")

                scores = {ObjectId(entry["user_id"]): entry["score"] for entry in payload.scores}
                participants_cursor = self.participants.find({"game_id": game["_id"]}, session=session)
                participants = [doc async for doc in participants_cursor]

                for part in participants:
                    user_id = part["user_id"]
                    part["score"] = scores.get(user_id, part.get("score", 0))

                winners = self._select_winners(participants)
                distribution = self._allocate_credits(game, winners)

                for entry in distribution:
                    if entry["amount"] <= 0:
                        continue
                    await self.wallet_service.credit(
                        str(entry["user_id"]),
                        amount=entry["amount"],
                        game_id=payload.game_id,
                        notes=entry.get("logic", "game_reward"),
                        session=session,
                    )

                now = datetime.now(timezone.utc)
                result_doc = {
                    "game_id": game["_id"],
                    "winners": [
                        {
                            "user_id": entry["user_id"],
                            "amount": entry["amount"],
                            "logic": entry.get("logic"),
                        }
                        for entry in distribution
                    ],
                    "distribution_logic": distribution[0].get("logic") if distribution else "",
                    "total_pool": game.get("pool_amount", 0),
                    "timestamp": now,
                }
                result = await self.results.insert_one(result_doc, session=session)
                await self.games.update_one(
                    {"_id": game["_id"]},
                    {
                        "$set": {
                            "state": "finished",
                            "updated_at": now,
                            "result_id": result.inserted_id,
                        }
                    },
                    session=session,
                )
                winner_ids = {entry["user_id"] for entry in distribution if entry.get("logic") != "host_fallback"}
                for part in participants:
                    status = "winner" if part["user_id"] in winner_ids else "eliminated"
                    await self.participants.update_one(
                        {"_id": part["_id"]},
                        {"$set": {"status": status, "last_seen": now}},
                        session=session,
                    )
                return result_doc

    def _select_winners(self, participants: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        active = [p for p in participants if p.get("status") != "left"]
        if not active:
            return []
        sorted_participants = sorted(active, key=lambda p: p.get("score", 0), reverse=True)
        top = sorted_participants[0]
        tied = [p for p in sorted_participants if p.get("score", 0) == top.get("score", 0)]
        return tied

    def _allocate_credits(self, game: dict[str, Any], winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pool = game.get("pool_amount", 0)
        if not winners:
            return []
        host_id = game.get("host_id")
        if len(winners) == 1:
            return [{"user_id": winners[0]["user_id"], "amount": pool, "logic": "single_winner"}]
        if len(winners) == 2:
            share = pool // 2
            remainder = pool % 2
            distribution = [
                {"user_id": winners[0]["user_id"], "amount": share, "logic": "tie_split"},
                {"user_id": winners[1]["user_id"], "amount": share, "logic": "tie_split"},
            ]
            if remainder and host_id:
                distribution.append({"user_id": host_id, "amount": remainder, "logic": "host_fallback"})
            return distribution
        return [{"user_id": winners[0]["user_id"], "amount": pool, "logic": "highest_score"}]
