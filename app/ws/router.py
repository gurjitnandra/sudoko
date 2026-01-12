"""WebSocket router handling authentication and real-time game updates."""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.services.games import GameService
from app.services.users import UserService
from app.ws import manager

router = APIRouter()

async def _fetch_user(db, user_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(user_id):
        return None
    return await db["users"].find_one({"_id": ObjectId(user_id)})


async def authenticate_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Authenticate a websocket handshake payload."""

    auth_type = (payload.get("type") or "jwt").lower()
    db = GameService()._db
    user_service = UserService(db)

    if auth_type == "jwt":
        token = payload.get("token")
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        try:
            claims = decode_access_token(token)
        except ValueError as exc:  # pragma: no cover - handled as HTTP error
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
        user_id = claims.get("sub")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported auth type")

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_doc = await _fetch_user(db, str(user_id))
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    public_user = user_service.to_public(user_doc).model_dump()
    return str(user_doc["_id"]), public_user


async def _game_snapshot(game_service: GameService, game_id: str) -> dict[str, Any]:
    participants = await game_service.list_participants(game_id)
    return {
        "event": "game_snapshot",
        "game_id": game_id,
        "participants": [
            {
                "user_id": str(entry["user_id"]),
                "score": entry.get("score", 0),
                "status": entry.get("status"),
                "ws_status": entry.get("ws_status"),
            }
            for entry in participants
        ],
    }


@router.websocket("/game/{game_id}")
async def websocket_game(websocket: WebSocket, game_id: str):
    await websocket.accept()
    try:
        initial = await websocket.receive_json()
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if initial.get("event") != "auth":
        await websocket.send_json({"event": "error", "message": "Authentication required"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    payload = initial.get("payload", {})
    try:
        user_id, public_user = await authenticate_payload(payload)
    except HTTPException as exc:
        await websocket.send_json({"event": "error", "message": exc.detail})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    game_service = GameService()
    await manager.connect(websocket, user_id=user_id, rooms=[f"game:{game_id}"])
    await game_service.set_participant_ws_status(game_id, user_id, "online")
    await manager.set_presence(user_id, status="online", context={"game_id": game_id})

    await websocket.send_json({"event": "auth_ok", "user": public_user, "game_id": game_id})
    await websocket.send_json(await _game_snapshot(game_service, game_id))
    await manager.broadcast(
        f"game:{game_id}",
        {
            "event": "presence_update",
            "game_id": game_id,
            "user_id": user_id,
            "status": "online",
        },
    )

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            if event == "heartbeat":
                await websocket.send_json({"event": "heartbeat_ack"})
                continue

            if event == "update_score":
                payload = data.get("payload", {})
                try:
                    delta = int(payload.get("delta", 0))
                except (TypeError, ValueError):
                    await websocket.send_json({"event": "error", "message": "Invalid score delta"})
                    continue
                target_user_id = str(payload.get("user_id") or user_id)
                game_doc = await game_service._get_game(game_id)
                if str(game_doc["host_id"]) != user_id:
                    await websocket.send_json({"event": "error", "message": "Only host may update scores"})
                    continue
                participant = await game_service.update_score(game_id, target_user_id, delta)
                await manager.broadcast(
                    f"game:{game_id}",
                    {
                        "event": "game_updated",
                        "game_id": game_id,
                        "participant": {
                            "user_id": str(participant["user_id"]),
                            "score": participant.get("score", 0),
                            "status": participant.get("status"),
                        },
                    },
                )
                continue

            await websocket.send_json({"event": "error", "message": "Unknown event"})

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, user_id=user_id)
        await game_service.set_participant_ws_status(game_id, user_id, "offline")
        await manager.set_presence(user_id, status="offline", context={"game_id": game_id})
        await manager.broadcast(
            f"game:{game_id}",
            {
                "event": "presence_update",
                "game_id": game_id,
                "user_id": user_id,
                "status": "offline",
            },
        )
