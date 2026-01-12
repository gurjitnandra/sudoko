from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

from session_manager import (
    PlayerNotFoundError,
    SessionManager,
    SessionNotFoundError,
    UnauthorizedPlayerError,
)

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
sessions = SessionManager()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/session", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    difficulty = (payload.get("difficulty") or "easy").strip().lower()
    ip_address = (request.remote_addr or "").strip()

    try:
        session, player = sessions.create_session(name, difficulty, ip_address)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    snapshot = sessions.snapshot(session.id)
    return jsonify({
        "success": True,
        "session": snapshot["session"],
        "player": player.to_dict(),
        "players": snapshot["players"],
        "state": snapshot["state"],
    })


@app.route("/api/session/<session_id>/join", methods=["POST"])
def join_session(session_id: str):
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "").strip()
    ip_address = (request.remote_addr or "").strip()

    try:
        player = sessions.join_session(session_id, name, ip_address)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    snapshot = sessions.snapshot(session_id)
    return jsonify({
        "success": True,
        "session": snapshot["session"],
        "player": player.to_dict(),
        "players": snapshot["players"],
        "state": snapshot["state"],
    })


@app.route("/api/session/<session_id>/leave", methods=["POST"])
def leave_session(session_id: str):
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("playerId")
    ip_address = (request.remote_addr or "").strip()

    if not isinstance(player_id, str):
        return jsonify({"success": False, "message": "playerId is required."}), 400

    try:
        removed_session, snapshot = sessions.leave_session(session_id, player_id, ip_address)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except PlayerNotFoundError:
        return jsonify({"success": False, "message": "Player not found."}), 404
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    if removed_session:
        return jsonify({"success": True, "message": "Session closed. All players have left."})

    return jsonify({
        "success": True,
        "message": "You have left the game.",
        **(snapshot or {}),
    })


@app.route("/api/session/<session_id>/state", methods=["GET"])
def session_state(session_id: str):
    try:
        snapshot = sessions.snapshot(session_id)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404

    return jsonify({
        "success": True,
        **snapshot,
    })


@app.route("/api/session/<session_id>/move", methods=["POST"])
def session_move(session_id: str):
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    value = payload.get("value")
    ip_address = (request.remote_addr or "").strip()

    if not isinstance(player_id, str):
        return jsonify({"success": False, "message": "playerId is required."}), 400

    if not isinstance(row, int) or not isinstance(col, int):
        return jsonify({"success": False, "message": "Row and column must be integers."}), 400

    if value is None:
        return jsonify({"success": False, "message": "Missing value."}), 400

    try:
        value = int(value)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Value must be an integer."}), 400

    try:
        session, _, success, message = sessions.apply_move(session_id, player_id, row, col, value)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except PlayerNotFoundError:
        return jsonify({"success": False, "message": "Player not found."}), 404
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    snapshot = sessions.snapshot(session_id)
    return jsonify({
        "success": success,
        "message": message,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    })


@app.route("/api/session/<session_id>/selection", methods=["POST"])
def session_selection(session_id: str):
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("playerId")
    row = payload.get("row")
    col = payload.get("col")
    ip_address = (request.remote_addr or "").strip()

    if not isinstance(player_id, str):
        return jsonify({"success": False, "message": "playerId is required."}), 400

    try:
        sessions.update_selection(session_id, player_id, row, col, ip_address)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except PlayerNotFoundError:
        return jsonify({"success": False, "message": "Player not found."}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    snapshot = sessions.snapshot(session_id)
    return jsonify({
        "success": True,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    })


@app.route("/api/session/<session_id>/reset", methods=["POST"])
def session_reset(session_id: str):
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("playerId")
    difficulty = payload.get("difficulty")
    ip_address = (request.remote_addr or "").strip()

    if not isinstance(player_id, str):
        return jsonify({"success": False, "message": "playerId is required."}), 400

    try:
        session = sessions.reset_session(session_id, player_id, difficulty, ip_address)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except PlayerNotFoundError:
        return jsonify({"success": False, "message": "Player not found."}), 404
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    snapshot = sessions.snapshot(session.id)
    return jsonify({
        "success": True,
        "session": snapshot["session"],
        "players": snapshot["players"],
        "state": snapshot["state"],
    })


@app.route("/api/session/<session_id>/chat", methods=["POST"])
def session_chat(session_id: str):
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("playerId")
    message = payload.get("message", "")
    ip_address = (request.remote_addr or "").strip()

    if not isinstance(player_id, str):
        return jsonify({"success": False, "message": "playerId is required."}), 400

    try:
        result = sessions.add_chat_message(session_id, player_id, message, ip_address)
    except SessionNotFoundError:
        return jsonify({"success": False, "message": "Session not found."}), 404
    except PlayerNotFoundError:
        return jsonify({"success": False, "message": "Player not found."}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except UnauthorizedPlayerError as exc:
        return jsonify({"success": False, "message": str(exc)}), 403

    return jsonify({
        "success": True,
        "chat": result["chat"],
        "session": result["session"],
        "players": result["players"],
        "state": result["state"],
    })


@app.route("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(BASE_DIR / "static", filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
