"""In-memory session store with automatic cleanup.

This module provides session management with the following features:
- Session persistence across page refreshes
- Automatic session expiration
- Thread-safe operations
- CSRF protection
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SessionStore:
    """Provide a best-effort, in-memory session store.

    Sessions live only for the lifetime of the process and are protected by an
    ``asyncio.Lock``. This should be sufficient for local development while the
    codebase migrates fully to stateless JWT authentication.
    """

    _sessions: Dict[str, dict] = {}
    _lock = asyncio.Lock()
    _ttl_minutes: int = 60

    def __init__(self) -> None:  # pragma: no cover - legacy compatibility
        pass

    async def create_session(self, user_id: str, user_agent: str, ip: str) -> dict:
        """Create a new session for the user.
        
        Args:
            user_id: The ID of the user
            user_agent: The user agent string from the request
            ip: The IP address of the client
            
        Returns:
            dict: Session information including session ID and CSRF token
        """
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(minutes=self._ttl_minutes)
        
        data = {
            "user_id": user_id,
            "user_agent": user_agent[:120],
            "ip": ip,
            "csrf": csrf_token,
            "created_at": now,
            "expires_at": expire_at,
            "last_activity": now,
            "is_active": True
        }
        
        async with self._lock:
            # Clean up any existing sessions for this user
            self._cleanup_sessions()
            # Store the new session
            self._sessions[session_id] = data
            
        logger.info(f"Created new session for user {user_id} (session_id: {session_id})")
        return {
            "id": session_id,
            "csrf": csrf_token,
            "expires_at": expire_at.isoformat(),
            "user_id": user_id
        }

    def _cleanup_sessions(self):
        """Remove expired sessions and mark inactive sessions."""
        now = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, session_data in list(self._sessions.items()):
            if now >= session_data["expires_at"]:
                expired_sessions.append(session_id)
                
        for session_id in expired_sessions:
            self._sessions.pop(session_id, None)
            
        return len(expired_sessions)
        
    async def refresh_session(self, session_id: str) -> bool:
        """Refresh a session's expiration time.
        
        Args:
            session_id: The session ID to refresh
            
        Returns:
            bool: True if session was refreshed, False otherwise
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False
                
            session = self._sessions[session_id]
            if not session.get("is_active", True):
                return False
                
            now = datetime.now(timezone.utc)
            session["last_activity"] = now
            session["expires_at"] = now + timedelta(minutes=self._ttl_minutes)
            return True
            
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data if it exists and is active.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            Optional[dict]: Session data if found and active, None otherwise
        """
        async with self._lock:
            self._cleanup_sessions()
            data = self._sessions.get(session_id)
            
        if not data:
            return None
        expires_at = data.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at)
            except ValueError:
                expiry = None
            if expiry and expiry < datetime.now(timezone.utc):
                await self.revoke_session(session_id)
                return None
        return data.copy()

    async def refresh_session(self, session_id: str) -> None:
        async with self._lock:
            data = self._sessions.get(session_id)
            if not data:
                return
            expire_at = datetime.now(timezone.utc) + timedelta(minutes=self._ttl_minutes)
            data["expires_at"] = expire_at.isoformat()

    async def revoke_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
