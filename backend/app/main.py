"""Pi Dashboard 2.0 — FastAPI Main-App.

Initial-Version 15.06.2026: Health-Check + DB-Init.
Vollstaendige Router-Implementation folgt in v2.0-beta.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db.base import init_db, engine
from sqlalchemy import text

# Logging-Setup
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pi-dashboard-2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App-Lifecycle: DB-Init beim Start, Cleanup beim Stop."""
    logger.info("Pi Dashboard 2.0 starting...")
    logger.info(f"Database: {settings.DATABASE_URL}")
    try:
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"DB-Init failed: {e}")
        raise
    yield
    logger.info("Pi Dashboard 2.0 shutting down.")
    engine.dispose()


app = FastAPI(
    title="Pi Dashboard 2.0",
    description="Hermes-Style Web-Dashboard fuer den lokalen PI Coding Agent — SQL-basiert",
    version="2.0.0-alpha",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Health-Check ===
@app.get("/api/health")
async def health() -> dict:
    """Liveness-Probe: Server + DB erreichbar?"""
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.error(f"DB-Health failed: {e}")
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "2.0.0-alpha",
        "database": settings.DATABASE_URL.split("://")[0],
        "database_ok": db_ok,
    }


# === Version-Info ===
@app.get("/api/version")
async def version() -> dict:
    """Versions-Info."""
    return {
        "version": "2.0.0-alpha",
        "phase": "Setup (15.06.2026)",
        "predecessor": "1.x (JSON-basiert)",
        "next_phase": "v2.0-beta — Backend-Endpoints auf SQL umstellen",
    }


# === Placeholder für v2.0-beta Router ===
# TODO: routers/kanban.py, routers/models.py, routers/roles.py etc. — alle SQL-basiert
