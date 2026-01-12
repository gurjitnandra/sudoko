"""Game lifecycle API routes."""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.core.exceptions import ConflictError, InsufficientCreditsError
from app.models.game import GameCreate, GameFinish, GameJoin, GameScoreUpdate
from app.services.games import GameService

router = APIRouter()


def get_game_service() -> GameService:
    return GameService()


def serialize_game(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "host_id": str(doc["host_id"]),
        "buy_in_credit": doc.get("buy_in_credit", 10),
        "state": doc.get("state"),
        "rules": doc.get("rules", {}),
        "participants": [str(pid) for pid in doc.get("participants", [])],
        "pool_amount": doc.get("pool_amount", 0),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "result_id": str(doc.get("result_id")) if doc.get("result_id") else None,
    }


def serialize_result(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": str(doc["game_id"]),
        "winners": [
            {
                "user_id": str(entry["user_id"]),
                "amount": entry["amount"],
                "logic": entry.get("logic"),
            }
            for entry in doc.get("winners", [])
        ],
        "distribution_logic": doc.get("distribution_logic"),
        "total_pool": doc.get("total_pool", 0),
        "timestamp": doc.get("timestamp"),
    }


@router.post("/create")
async def create_game(
    payload: GameCreate,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        doc = await game_service.create_game(str(current_user["_id"]), payload.buy_in_credit, payload.rules)
    except (ValueError, InsufficientCreditsError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"game": serialize_game(doc)}


@router.post("/join")
async def join_game(
    payload: GameJoin,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        doc = await game_service.join_game(payload.game_id, str(current_user["_id"]))
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"game": serialize_game(doc)}


@router.post("/start")
async def start_game(
    payload: GameJoin,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        doc = await game_service.start_game(payload.game_id, str(current_user["_id"]))
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"game": serialize_game(doc)}


@router.post("/update-score")
async def update_score(
    payload: GameScoreUpdate,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        participant = await game_service.update_score(payload.game_id, payload.user_id, payload.delta)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "participant": {
            "user_id": str(participant["user_id"]),
            "game_id": str(participant["game_id"]),
            "score": participant.get("score", 0),
            "status": participant.get("status"),
        }
    }


@router.post("/finish")
async def finish_game(
    payload: GameFinish,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        result = await game_service.finish_game(payload, str(current_user["_id"]))
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"result": serialize_result(result)}


@router.get("/{game_id}")
async def get_game(
    game_id: str,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    try:
        doc = await game_service._get_game(game_id)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"game": serialize_game(doc)}


@router.get("/result/{game_id}")
async def get_game_result(
    game_id: str,
    current_user=Depends(get_current_user),
    game_service: GameService = Depends(get_game_service),
):
    doc = await game_service.results.find_one({"game_id": ObjectId(game_id)})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    return {"result": serialize_result(doc)}
