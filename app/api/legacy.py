"""Legacy Sudoku session endpoints maintained for existing front-end compatibility."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from session_manager import (
    PlayerNotFoundError,
    SessionManager,
    SessionNotFoundError,
    UnauthorizedPlayerError,
)

router = APIRouter()
sessions = SessionManager()


@router.post("/session")
async def create_session(request: Request):
    payload = await request.json() if request.method == "POST" else {}
    name = (payload.get("name") or "").strip()
    difficulty = (payload.get("difficulty") or "easy").strip().lower()
    ip_address = (request.client.host if request.client else "").strip()

    try:
        session, player = sessions.create_session(name, difficulty, ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session.id)
    return {
        "success": True,
        "session": snapshot["session"],
        "player": player.to_dict(),
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/join")
async def join_session(session_id: str, request: Request):
    payload = await request.json()
    name = (payload.get("name") or "").strip()
    ip_address = (request.client.host if request.client else "").strip()

    try:
        player = sessions.join_session(session_id, name, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session_id)
    return {
        "success": True,
        "session": snapshot["session"],
        "player": player.to_dict(),
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/leave")
async def leave_session(session_id: str, request: Request):
    payload = await request.json()
    player_id = payload.get("playerId")
    ip_address = (request.client.host if request.client else "").strip()

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        removed_session, snapshot = sessions.leave_session(session_id, player_id, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if removed_session:
        return {"success": True, "message": "Session closed. All players have left."}

    return {
        "success": True,
        "message": "You have left the game.",
        **(snapshot or {}),
    }


@router.get("/session/{session_id}/state")
async def session_state(session_id: str):
    try:
        snapshot = sessions.snapshot(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    return {"success": True, **snapshot}


@router.post("/session/{session_id}/move")
async def session_move(session_id: str, request: Request):
    payload = await request.json()
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    value = payload.get("value")
    ip_address = (request.client.host if request.client else "").strip()

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")
    if not isinstance(row, int) or not isinstance(col, int):
        raise HTTPException(status_code=400, detail="Row and column must be integers.")
    if value is None:
        raise HTTPException(status_code=400, detail="Missing value.")

    try:
        value_int = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Value must be an integer.") from exc

    try:
        sessions.apply_move(session_id, player_id, row, col, value_int, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session_id)
    return {
        "success": True,
        "message": "Move processed.",
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/selection")
async def session_selection(session_id: str, request: Request):
    payload = await request.json()
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    ip_address = (request.client.host if request.client else "").strip()

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        sessions.update_selection(session_id, player_id, row, col, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session_id)
    return {
        "success": True,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/reset")
async def session_reset(session_id: str, request: Request):
    payload = await request.json()
    player_id = payload.get("playerId")
    difficulty = payload.get("difficulty")
    ip_address = (request.client.host if request.client else "").strip()

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        session = sessions.reset_session(session_id, player_id, difficulty, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session.id)
    return {
        "success": True,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/chat")
async def session_chat(session_id: str, request: Request):
    payload = await request.json()
    player_id = payload.get("playerId")
    message = payload.get("message", "")
    ip_address = (request.client.host if request.client else "").strip()

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        result = sessions.add_chat_message(session_id, player_id, message, ip_address)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return {
        "success": True,
        "chat": result["chat"],
        "session": result["session"],
        "players": result["players"],
        "state": result["state"],
    }
