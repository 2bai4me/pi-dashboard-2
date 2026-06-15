"""Pi Dashboard 2.0 — FastAPI Main-App.

v2.0-beta: Vollstaendige Router-Implementation (Projects, Tasks, Models, Roles)
Alle Daten werden in SQL gespeichert (SQLite/PostgreSQL via SQLAlchemy 2.0).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db.base import init_db, engine
from .services.role_service import RoleService

# Logging-Setup
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pi-dashboard-2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App-Lifecycle: DB-Init + Role-Defaults beim Start."""
    logger.info("Pi Dashboard 2.0 starting...")
    logger.info(f"Database: {settings.DATABASE_URL}")
    try:
        init_db()
        logger.info("Database initialized.")
        # Seed default roles
        from .db.base import SessionLocal
        with SessionLocal() as db:
            added = RoleService.seed_defaults(db)
            if added:
                logger.info(f"Seeded {added} default roles.")
    except Exception as e:
        logger.error(f"Init failed: {e}")
        raise
    yield
    logger.info("Pi Dashboard 2.0 shutting down.")
    engine.dispose()


app = FastAPI(
    title="Pi Dashboard 2.0",
    description="Hermes-Style Web-Dashboard fuer den lokalen PI Coding Agent — SQL-basiert",
    version="2.0.0-beta",
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

# === Routers einbinden ===
from .routers import projects, tasks, models, roles  # noqa: E402

app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(models.router)
app.include_router(roles.router)


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
        "version": "2.0.0-beta",
        "database": settings.DATABASE_URL.split("://")[0],
        "database_ok": db_ok,
    }


@app.get("/api/version")
async def version() -> dict:
    return {
        "version": "2.0.0-beta",
        "phase": "Backend-Endpoints auf SQL (15.06.2026)",
        "predecessor": "1.x (JSON-basiert)",
        "next_phase": "v2.0-rc — Frontend-Anbindung + Performance-Tests",
    }


# === Analytics-Endpoints (Bonus: zeigen SQL-Staerke) ===
from sqlalchemy.orm import Session  # noqa: E402
from fastapi import Depends  # noqa: E402
from sqlalchemy import select, func as sqlfunc  # noqa: E402
from .db.base import get_db  # noqa: E402
from .auth import require_auth as _require_auth  # noqa: E402
from .models.task import Task  # noqa: E402
from .models.history import TaskHistory  # noqa: E402
from .models.token_usage import TokenUsage  # noqa: E402


@app.get("/api/analytics/summary")
async def analytics_summary(
    db: Session = Depends(get_db),
    _user: str = Depends(_require_auth),
):
    """Globale Analytics — das ist was SQL kann, JSON nicht."""
    total_tasks = db.execute(select(sqlfunc.count(Task.id))).scalar()
    total_history = db.execute(select(sqlfunc.count(TaskHistory.id))).scalar()
    total_token_rows = db.execute(select(sqlfunc.count(TokenUsage.id))).scalar()
    total_cost = db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0))
    ).scalar() or 0
    total_in = db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_in), 0))
    ).scalar() or 0
    total_out = db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_out), 0))
    ).scalar() or 0
    # Status-Distribution
    status_dist = db.execute(
        select(Task.status, sqlfunc.count(Task.id).label("cnt"))
        .group_by(Task.status)
    ).all()
    # Cost by Provider
    cost_by_prov = db.execute(
        select(TokenUsage.provider, sqlfunc.sum(TokenUsage.cost_usd).label("cost"))
        .group_by(TokenUsage.provider)
    ).all()
    return {
        "totals": {
            "tasks": total_tasks,
            "history_entries": total_history,
            "token_usage_records": total_token_rows,
            "tokens_in": int(total_in),
            "tokens_out": int(total_out),
            "cost_usd": float(total_cost),
        },
        "status_distribution": {s: c for s, c in status_dist},
        "cost_by_provider": {p: float(c) for p, c in cost_by_prov if p},
    }
