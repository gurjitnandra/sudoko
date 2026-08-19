"""Authentication API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import get_current_user, get_user_service
from app.core.exceptions import AuthenticationError, BadRequestError
from app.core.config import cookie_secure
from app.core.session import SessionStore
from app.schemas.auth import Token, UserLogin, UserRegister, SessionRefresh, RefreshTokenPayload
from app.services.auth import AuthService

router = APIRouter()


def get_auth_service(user_service = Depends(get_user_service)) -> AuthService:
    return AuthService(user_service=user_service)


@router.post("/register")
async def register_user(payload: UserRegister, auth_service: AuthService = Depends(get_auth_service)):
    try:
        result = await auth_service.register_user(payload)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.post("/login", response_model=Token)
async def login_user(
    request: Request,
    payload: UserLogin,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    # Get user agent and IP for session tracking
    user_agent = request.headers.get("user-agent", "")
    client_host = request.client.host if request.client else "0.0.0.0"
    
    # Create a new session
    session_store = SessionStore()
    try:
        result = await auth_service.login(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # ``login`` returns {"tokens": TokenPair, "user": UserPublic}
    tokens = result["tokens"]
    response_payload = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
        "user_id": tokens.user_id,
    }

    session = await session_store.create_session(
        user_id=tokens.user_id,
        user_agent=user_agent,
        ip=client_host,
    )
    response_payload["session_id"] = session["id"]

    # HTTP-only session cookie (``secure`` only outside local development, so
    # plain-HTTP LAN testing still receives the cookie).
    response.set_cookie(
        key="session_id",
        value=session["id"],
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=3600  # 1 hour
    )

    return response_payload


@router.post("/refresh")
async def refresh_tokens(
    payload: RefreshTokenPayload,
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh access token using a refresh token."""
    try:
        token_pair = await auth_service.refresh(payload.refresh_token)
        
        # Create a new session if the refresh was successful
        user_agent = request.headers.get("user-agent", "")
        client_host = request.client.host if request.client else "0.0.0.1"
        
        session_store = SessionStore()
        session = await session_store.create_session(
            user_id=token_pair.user_id,
            user_agent=user_agent,
            ip=client_host
        )
        
        # Set the session cookie
        response.set_cookie(
            key="session_id",
            value=session["id"],
            httponly=True,
            secure=cookie_secure(),
            samesite="lax",
            max_age=3600  # 1 hour
        )
        
        return {
            "access_token": token_pair.access_token,
            "refresh_token": token_pair.refresh_token,
            "token_type": "bearer",
            "expires_in": token_pair.expires_in,
            "session_id": session["id"]
        }
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"}
        ) from exc


@router.post("/refresh-session")
async def refresh_session(
    request: Request,
    session_refresh: SessionRefresh,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh an existing session to extend its lifetime."""
    session_store = SessionStore()
    session_id = session_refresh.session_id or request.cookies.get("session_id")
    
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session ID is required"
        )
    
    refreshed = await session_store.refresh_session(session_id)
    if not refreshed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    return {"status": "session_refreshed"}


@router.post("/logout")
async def logout_user(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Log out the current user by revoking their session."""
    session_store = SessionStore()
    session_id = request.cookies.get("session_id")
    
    if session_id:
        await session_store.revoke_session(session_id)
    
    # Clear the session cookie
    response.delete_cookie(
        "session_id",
        httponly=True,
        secure=cookie_secure(),
        samesite="lax"
    )
    
    return {"message": "Successfully logged out"}


@router.get("/me")
async def get_me(
    current_user=Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    return {"user": auth_service.user_service.to_public(current_user)}
