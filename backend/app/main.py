"""Pi Dashboard 2.0 — FastAPI Main-App.

v2.0-rc: Vollstaendige Router + Analytics + Index-Audit
Alle Daten werden in SQL gespeichert (SQLite/PostgreSQL via SQLAlchemy 2.0).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select, func as sqlfunc
from sqlalchemy.orm import Session

from .config import settings
from .db.base import init_db, engine, SessionLocal, get_db
from .auth import require_auth
from .services.role_service import RoleService
from .models.task import Task
from .models.history import TaskHistory
from .models.token_usage import TokenUsage
from .models.pricing import ModelPricing

# Logging
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
    version="2.0.0-rc",
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

# === Routers ===
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
        "version": "2.0.0-rc",
        "database": settings.DATABASE_URL.split("://")[0],
        "database_ok": db_ok,
    }


@app.get("/api/version")
async def version() -> dict:
    return {
        "version": "2.0.0-rc",
        "phase": "Index-Audit + Performance-Optimierung (15.06.2026)",
        "predecessor": "2.0.0-beta",
        "next_phase": "v2.0-stable — Migration v1 + Production-Readiness",
    }


# === Analytics: Summary ===
@app.get("/api/analytics/summary")
async def analytics_summary(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Globale Analytics — SQL-Aggregation."""
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
    status_dist = db.execute(
        select(Task.status, sqlfunc.count(Task.id).label("cnt"))
        .group_by(Task.status)
    ).all()
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


# === Analytics: Index-Audit (welche DB-Indizes werden genutzt?) ===
@app.post("/api/analytics/analyze")
async def run_analyze(
    _user: str = Depends(require_auth),
):
    """Fuehrt ANALYZE auf der DB aus — sammelt sqlite_stat1 fuer EXPLAIN-Ausgaben."""
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()
    return {"ok": True, "message": "ANALYZE ausgefuehrt"}


@app.get("/api/analytics/index-usage")
async def index_usage(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert Index-Usage-Statistiken + Drop-Empfehlungen."""
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()

    rows = db.execute(text('''
        SELECT tbl, idx, stat FROM sqlite_stat1 ORDER BY tbl, idx
    ''')).fetchall()

    out = []
    for tbl, idx, stat_str in rows:
        parts = stat_str.split()
        if not parts:
            continue
        try:
            total_rows = int(parts[0])
        except (ValueError, IndexError):
            continue
        if len(parts) >= 2:
            try:
                avg_per_key = float(parts[1])
            except ValueError:
                avg_per_key = total_rows
        else:
            avg_per_key = total_rows
        selectivity = round(avg_per_key / total_rows, 3) if total_rows > 0 else 0
        if selectivity < 0.1:
            recommendation = "excellent"
        elif selectivity < 0.3:
            recommendation = "good"
        elif selectivity < 0.7:
            recommendation = "marginal"
        else:
            recommendation = "poor"
        out.append({
            "table": tbl,
            "index": idx,
            "rows": total_rows,
            "selectivity": selectivity,
            "recommendation": recommendation,
        })
    return {"indexes": out, "analyzed_at": datetime.utcnow().isoformat()}
