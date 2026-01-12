from __future__ import annotations

import secrets
import string
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sudoku_core import Sudoku

_SESSION_ID_CHARS = string.ascii_uppercase + string.digits
_PLAYER_COLORS = [
    "#f2a900",
    "#2dce89",
    "#45aaf2",
    "#a55eea",
    "#ff6b6b",
    "#fd9644",
    "#1dd1a1",
    "#54a0ff",
    "#ff9f43",
    "#48dbfb",
]

_MISTAKE_LIMIT = 3


def _generate_session_id(length: int = 6) -> str:
    return "".join(secrets.choice(_SESSION_ID_CHARS) for _ in range(length))


def _generate_player_id() -> str:
    return secrets.token_hex(8)


@dataclass
class Player:
    id: str
    name: str
    color: str
    score: int = 0
    is_host: bool = False
    mistakes: int = 0
    eliminated: bool = False
    ip_address: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "score": self.score,
            "isHost": self.is_host,
            "mistakes": self.mistakes,
            "eliminated": self.eliminated,
        }


class SessionNotFoundError(KeyError):
    pass


class PlayerNotFoundError(KeyError):
    pass


class UnauthorizedPlayerError(PermissionError):
    pass


class GameSession:
    def __init__(self, session_id: str, difficulty: str = "easy"):
        self.id = session_id
        self._difficulty = difficulty
        self._sudoku = Sudoku(difficulty)
        self._lock = threading.Lock()
        self._players: Dict[str, Player] = {}
        self._player_order: List[str] = []
        self._cell_claims: List[List[Optional[str]]] = [
            [None for _ in range(Sudoku.BOARD_SIZE)] for _ in range(Sudoku.BOARD_SIZE)
        ]
        self._host_id: Optional[str] = None
        self._selections: Dict[str, Optional[Tuple[int, int]]] = {}
        self._chat_log: List[dict] = []
        self._chat_serial = 0
        self._departed_ips: set[str] = set()
        self._last_reset_by: Optional[str] = None
        self._last_reset_at: Optional[datetime] = None

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    @property
    def difficulty(self) -> str:
        return self._sudoku.difficulty

    @property
    def sudoku(self) -> Sudoku:
        return self._sudoku

    def add_player(self, name: str, *, is_host: bool = False, ip_address: str = "") -> Player:
        ip_key = ip_address.strip() if ip_address else ""
        if ip_key and ip_key in self._departed_ips:
            raise ValueError("This device has left the lobby and cannot rejoin.")

        player_id = _generate_player_id()
        color = _PLAYER_COLORS[len(self._players) % len(_PLAYER_COLORS)]
        player = Player(id=player_id, name=name, color=color, is_host=is_host, ip_address=ip_key)
        self._players[player_id] = player
        self._player_order.append(player_id)
        self._selections[player_id] = None
        if is_host:
            self._host_id = player_id
        return player

    def get_player(self, player_id: str) -> Player:
        try:
            return self._players[player_id]
        except KeyError as exc:
            raise PlayerNotFoundError(player_id) from exc

    def remove_player(self, player_id: str) -> None:
        if player_id not in self._players:
            raise PlayerNotFoundError(player_id)

        player = self._players.pop(player_id)
        self._player_order = [pid for pid in self._player_order if pid != player_id]
        self._selections.pop(player_id, None)
        if player.ip_address:
            self._departed_ips.add(player.ip_address)

        if player.is_host:
            player.is_host = False

        for row in range(Sudoku.BOARD_SIZE):
            for col in range(Sudoku.BOARD_SIZE):
                if self._cell_claims[row][col] == player_id:
                    self._cell_claims[row][col] = None

        if self._host_id == player_id:
            self._host_id = self._player_order[0] if self._player_order else None
            for pid, session_player in self._players.items():
                session_player.is_host = pid == self._host_id

    def set_selection(self, player_id: str, row: Optional[int], col: Optional[int]) -> None:
        if player_id not in self._players:
            raise PlayerNotFoundError(player_id)

        player = self._players[player_id]
        if player.eliminated:
            self._selections[player_id] = None
            return

        if row is None or col is None:
            self._selections[player_id] = None
            return

        if not isinstance(row, int) or not isinstance(col, int):
            raise ValueError("Row and column must be integers.")

        if not (0 <= row < Sudoku.BOARD_SIZE and 0 <= col < Sudoku.BOARD_SIZE):
            raise ValueError("Row or column out of range.")

        self._selections[player_id] = (row, col)

    def add_chat_message(self, player_id: str, message: str) -> dict:
        if player_id not in self._players:
            raise PlayerNotFoundError(player_id)

        content = (message or "").strip()
        if not content:
            raise ValueError("Message cannot be empty.")

        player = self._players[player_id]
        timestamp = datetime.now(timezone.utc).isoformat()
        self._chat_serial += 1
        entry = {
            "id": f"{self._chat_serial}",
            "playerId": player.id,
            "playerName": player.name,
            "color": player.color,
            "message": content[:300],
            "timestamp": timestamp,
        }
        self._chat_log.append(entry)
        if len(self._chat_log) > 200:
            self._chat_log = self._chat_log[-200:]
        return entry

    def ensure_host(self, player_id: str) -> None:
        if self._host_id != player_id:
            raise UnauthorizedPlayerError("Only the host can perform this action.")

    def players_snapshot(self) -> List[dict]:
        players = [self._players[player_id] for player_id in self._player_order if player_id in self._players]
        return [player.to_dict() for player in sorted(players, key=lambda p: (-p.score, p.name.lower()))]

    def state_snapshot(self) -> dict:
        return {
            "sessionId": self.id,
            "difficulty": self._sudoku.difficulty,
            "board": self._sudoku.get_state(),
            "givens": self._sudoku.get_givens(),
            "complete": self._sudoku.is_complete(),
            "claims": [row[:] for row in self._cell_claims],
            "selections": {
                player_id: {"row": coords[0], "col": coords[1]}
                for player_id, coords in self._selections.items()
                if coords is not None
            },
            "chatLog": [entry.copy() for entry in self._chat_log],
            "mistakeLimit": _MISTAKE_LIMIT,
            "lastReset": {
                "playerId": self._last_reset_by,
                "timestamp": self._last_reset_at.isoformat() if self._last_reset_at else None,
            },
        }

    def apply_move(self, player_id: str, row: int, col: int, value: int) -> Tuple[bool, str]:
        if player_id not in self._players:
            raise PlayerNotFoundError(player_id)

        if not (0 <= row < Sudoku.BOARD_SIZE and 0 <= col < Sudoku.BOARD_SIZE):
            return False, "Row or column out of range."

        player = self._players[player_id]

        if player.eliminated:
            return False, "You have been eliminated after three mistakes."

        if self._sudoku.is_given(row, col):
            return False, "Cannot change a given cell."

        current_value = self._sudoku.state[row][col]
        target_value = self._sudoku.solution[row][col]

        if value == 0:
            if current_value == 0:
                return True, "Cell already empty."
            if current_value == target_value:
                return False, "Cannot clear a solved cell."
            self._sudoku.set_value(row, col, 0)
            self._cell_claims[row][col] = None
            return True, "Cell cleared."

        if not (1 <= value <= 9):
            return False, "Value must be between 1 and 9."

        if current_value == target_value:
            return False, "Cell already filled with the correct value."

        if value != target_value:
            player.mistakes += 1
            remaining = max(_MISTAKE_LIMIT - player.mistakes, 0)
            if player.mistakes >= _MISTAKE_LIMIT:
                player.eliminated = True
                self._selections[player_id] = None
                return False, "Incorrect value. You have reached 3 mistakes and lost the game."
            plural = "s" if remaining != 1 else ""
            return False, f"Incorrect value. {remaining} mistake{plural} remaining."

        applied = self._sudoku.set_value(row, col, value)
        if not applied:
            return False, "Move rejected."

        if value == 0:
            self._cell_claims[row][col] = None
            return True, "Cell cleared."

        if current_value == 0:
            player.score += 1
        self._cell_claims[row][col] = player_id
        return True, "Move applied."

    def reset(self, difficulty: Optional[str] = None) -> None:
        self._sudoku.reset(difficulty)
        self._cell_claims = [
            [None for _ in range(Sudoku.BOARD_SIZE)] for _ in range(Sudoku.BOARD_SIZE)
        ]
        for player in self._players.values():
            player.score = 0
            player.mistakes = 0
            player.eliminated = False
        self._last_reset_by = None
        self._last_reset_at = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, GameSession] = {}
        self._lock = threading.Lock()

    def create_session(self, host_name: str, difficulty: str = "easy", ip_address: str = "") -> Tuple[GameSession, Player]:
        if not host_name:
            raise ValueError("Host name is required.")

        with self._lock:
            session_id = _generate_session_id()
            while session_id in self._sessions:
                session_id = _generate_session_id()
            session = GameSession(session_id, difficulty)
            host_player = session.add_player(host_name, is_host=True, ip_address=ip_address)
            self._sessions[session_id] = session
        return session, host_player

    def get_session(self, session_id: str) -> GameSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SessionNotFoundError(session_id) from exc

    def join_session(self, session_id: str, player_name: str, ip_address: str = "") -> Player:
        if not player_name:
            raise ValueError("Player name is required.")
        session = self.get_session(session_id)
        with session.lock:
            return session.add_player(player_name, ip_address=ip_address)

    def leave_session(self, session_id: str, player_id: str, ip_address: str = "") -> Tuple[bool, Optional[dict]]:
        session = self.get_session(session_id)
        with session.lock:
            player = session.get_player(player_id)
            if player.ip_address and ip_address and player.ip_address != ip_address:
                raise UnauthorizedPlayerError("Device mismatch.")
            session.remove_player(player_id)
            if not session.players_snapshot():
                should_cleanup = True
                snapshot = None
            else:
                should_cleanup = False
                snapshot = {
                    "session": {
                        "id": session.id,
                        "difficulty": session.difficulty,
                    },
                    "players": session.players_snapshot(),
                    "state": session.state_snapshot(),
                }

        if should_cleanup:
            with self._lock:
                self._sessions.pop(session_id, None)

        return should_cleanup, snapshot

    def apply_move(self, session_id: str, player_id: str, row: int, col: int, value: int, ip_address: str = "") -> Tuple[GameSession, Player, bool, str]:
        session = self.get_session(session_id)
        with session.lock:
            player = session.get_player(player_id)
            if player.ip_address and ip_address and player.ip_address != ip_address:
                raise UnauthorizedPlayerError("Device mismatch.")
            success, message = session.apply_move(player_id, row, col, value)
            return session, player, success, message

    def update_selection(self, session_id: str, player_id: str, row: Optional[int], col: Optional[int], ip_address: str = "") -> GameSession:
        session = self.get_session(session_id)
        with session.lock:
            player = session.get_player(player_id)
            if player.ip_address and ip_address and player.ip_address != ip_address:
                raise UnauthorizedPlayerError("Device mismatch.")
            session.set_selection(player_id, row, col)
            return session

    def reset_session(self, session_id: str, player_id: str, difficulty: Optional[str], ip_address: str = "") -> GameSession:
        session = self.get_session(session_id)
        with session.lock:
            session.ensure_host(player_id)
            player = session.get_player(player_id)
            if player.ip_address and ip_address and player.ip_address != ip_address:
                raise UnauthorizedPlayerError("Device mismatch.")
            session.reset(difficulty)
            session._last_reset_by = player_id
            session._last_reset_at = datetime.now(timezone.utc)
            return session

    def add_chat_message(self, session_id: str, player_id: str, message: str, ip_address: str = "") -> dict:
        session = self.get_session(session_id)
        with session.lock:
            player = session.get_player(player_id)
            if player.ip_address and ip_address and player.ip_address != ip_address:
                raise UnauthorizedPlayerError("Device mismatch.")
            entry = session.add_chat_message(player_id, message)
            return {
                "chat": entry,
                "session": {
                    "id": session.id,
                    "difficulty": session.difficulty,
                },
                "players": session.players_snapshot(),
                "state": session.state_snapshot(),
            }

    def snapshot(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        with session.lock:
            return {
                "session": {
                    "id": session.id,
                    "difficulty": session.difficulty,
                },
                "players": session.players_snapshot(),
                "state": session.state_snapshot(),
            }


__all__ = [
    "SessionManager",
    "SessionNotFoundError",
    "PlayerNotFoundError",
    "UnauthorizedPlayerError",
]
