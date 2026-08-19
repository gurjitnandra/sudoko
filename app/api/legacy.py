"""Legacy Sudoku session endpoints maintained for existing front-end compatibility."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import cookie_secure
from session_manager import (
    PlayerNotFoundError,
    SessionManager,
    SessionNotFoundError,
    UnauthorizedPlayerError,
)

router = APIRouter()
sessions = SessionManager()

CLIENT_COOKIE = "sudoku_client"
CLIENT_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def get_client_key(request: Request, response: Response) -> str:
    """Identify the calling *browser*, not the machine.

    Player ownership used to be keyed on ``request.client.host``, which made
    every browser and tab on one machine (or behind one NAT) look like a single
    player. A per-browser cookie keeps the "you cannot rejoin after leaving"
    and "only your browser can move your player" rules intact while letting
    several browsers on the same computer play against each other.
    """

    key = (request.cookies.get(CLIENT_COOKIE) or "").strip()
    if not key:
        key = secrets.token_urlsafe(16)

    response.set_cookie(
        key=CLIENT_COOKIE,
        value=key,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=CLIENT_COOKIE_MAX_AGE,
    )
    return key


@router.post("/session")
async def create_session(request: Request, response: Response):
    payload = await request.json() if request.method == "POST" else {}
    name = (payload.get("name") or "").strip()
    difficulty = (payload.get("difficulty") or "easy").strip().lower()
    client_key = get_client_key(request, response)

    try:
        session, player = sessions.create_session(name, difficulty, client_key)
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
async def join_session(session_id: str, request: Request, response: Response):
    payload = await request.json()
    name = (payload.get("name") or "").strip()
    client_key = get_client_key(request, response)

    try:
        player = sessions.join_session(session_id, name, client_key)
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
async def leave_session(session_id: str, request: Request, response: Response):
    payload = await request.json()
    player_id = payload.get("playerId")
    client_key = get_client_key(request, response)

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        removed_session, snapshot = sessions.leave_session(session_id, player_id, client_key)
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
async def session_move(session_id: str, request: Request, response: Response):
    payload = await request.json()
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    value = payload.get("value")
    client_key = get_client_key(request, response)

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
        _, _, success, message = sessions.apply_move(session_id, player_id, row, col, value_int, client_key)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found.")
    except UnauthorizedPlayerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    snapshot = sessions.snapshot(session_id)
    return {
        "success": success,
        "message": message,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    }


@router.post("/session/{session_id}/selection")
async def session_selection(session_id: str, request: Request, response: Response):
    payload = await request.json()
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    client_key = get_client_key(request, response)

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        sessions.update_selection(session_id, player_id, row, col, client_key)
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
async def session_reset(session_id: str, request: Request, response: Response):
    payload = await request.json()
    player_id = payload.get("playerId")
    difficulty = payload.get("difficulty")
    client_key = get_client_key(request, response)

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        session = sessions.reset_session(session_id, player_id, difficulty, client_key)
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
async def session_chat(session_id: str, request: Request, response: Response):
    payload = await request.json()
    player_id = payload.get("playerId")
    message = payload.get("message", "")
    client_key = get_client_key(request, response)

    if not isinstance(player_id, str):
        raise HTTPException(status_code=400, detail="playerId is required.")

    try:
        result = sessions.add_chat_message(session_id, player_id, message, client_key)
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
