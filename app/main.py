"""FastAPI application entry point."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.api import legacy as legacy_router
from app.api.v1 import auth as auth_router
from app.api.v1 import games as games_router
from app.api.v1 import wallet as wallet_router
from app.core.config import get_settings
from app.ws.router import router as ws_router

logger = logging.getLogger("sudoku.backend")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    origins = settings.backend_cors_origins
    if isinstance(origins, str):
        origins = [origin.strip() for origin in origins.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        context = {
            "request": request,
            "user": None  # Will be populated by auth middleware if user is logged in
        }
        return templates.TemplateResponse("index.html", context)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(wallet_router.router, prefix="/api/v1/wallet", tags=["wallet"])
    app.include_router(games_router.router, prefix="/api/v1/game", tags=["game"])
    app.include_router(legacy_router.router, prefix="/api", tags=["legacy"])
    app.include_router(ws_router, prefix="/ws")

    return app


app = create_app()
