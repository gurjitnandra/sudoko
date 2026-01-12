"""WebSocket package exports."""
from __future__ import annotations

from app.ws.manager import ConnectionManager

manager = ConnectionManager()

__all__ = ["manager", "ConnectionManager"]
