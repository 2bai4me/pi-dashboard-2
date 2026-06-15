"""Pi Dashboard 2.0 — FastAPI Main-App.

v2.0-rc: Vollstaendige Router + Analytics + Index-Audit
Alle Daten werden in SQL gespeichert (SQLite/PostgreSQL via SQLAlchemy 2.0).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select, func as sqlfunc
from sqlalchemy.orm import Session

from .config import settings
from .db.base import init_db, engine, SessionLocal, get_db
from .auth import require_auth
from .services.role_service import RoleService
from .scheduler import start_scheduler, stop_scheduler
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

# JSON-Logging Setup (Production-Ready) — toggle via LOG_FORMAT=json
import os
if os.getenv("LOG_FORMAT", "text").lower() == "json":
    import json
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "ts": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
    for h in logging.root.handlers:
        h.setFormatter(JsonFormatter())


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
        # Auto-Backup-Scheduler starten
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logger.warning(f"Backup-Scheduler konnte nicht starten: {e}")
    except Exception as e:
        logger.error(f"Init failed: {e}")
        raise
    yield
    logger.info("Pi Dashboard 2.0 shutting down.")
    from .scheduler import stop_scheduler
    stop_scheduler()
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
from .routers import projects, tasks, models, roles, brainstorm  # noqa: E402
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(models.router)
app.include_router(roles.router)
app.include_router(brainstorm.router)


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


@app.get("/api/health/db-deep")
async def health_db_deep(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Tieferer Health-Check fuer Kubernetes-Probes.

    Prueft: DB-Connection, alle erwarteten Tabellen, Indizes, Alembic-Version.
    """
    checks = {"database_connection": False, "tables_exist": False,
              "indexes_count": 0, "alembic_version": None}
    overall_ok = False
    try:
        db.execute(text("SELECT 1"))
        checks["database_connection"] = True
        expected_tables = ["projects", "tasks", "task_history", "roles",
                           "token_usage", "model_pricing", "brainstorm_entries",
                           "requirement_docs", "review_pipelines",
                           "implementation_steps", "event_log"]
        for t in expected_tables:
            exists = db.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
            ), {"t": t}).first()
            if not exists:
                checks["tables_exist"] = False
                break
        else:
            checks["tables_exist"] = True
        checks["indexes_count"] = db.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
        )).scalar() or 0
        checks["alembic_version"] = db.execute(text(
            "SELECT version_num FROM alembic_version"
        )).scalar()
        overall_ok = (checks["database_connection"] and checks["tables_exist"]
                      and checks["indexes_count"] > 10)
    except Exception as e:
        logger.error(f"DB-Deep-Health failed: {e}")
    return {
        "status": "ok" if overall_ok else "degraded",
        "checks": checks,
        "checked_at": datetime.utcnow().isoformat(),
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


# === SSE: Server-Sent Events fuer Live-Updates (SQLite-basiert, Multi-Process-safe) ===
import asyncio
import json as _json
from sse_starlette.sse import EventSourceResponse
from . import events as _events
from fastapi import Query as _Query


@app.get("/api/kanban/events/{project_id}")
async def kanban_events(
    project_id: str,
    last_event_id: int = _Query(0, ge=0, description="Letzte gesehene Event-ID fuer Resume"),
    _user: str = Depends(require_auth),
):
    """SSE-Stream mit SQLite-Long-Polling (Multi-Process-safe).

    Events: task_created, task_status_changed, task_priority_changed,
    task_usage_reported, project_mode_changed.
    """
    _events.ensure_table()

    async def event_generator():
        yield {
            "event": "connected",
            "data": _json.dumps({
                "project_id": project_id,
                "ts": datetime.utcnow().isoformat(),
                "last_event_id": last_event_id,
            }),
        }
        cur_id = last_event_id
        try:
            while True:
                events = await asyncio.to_thread(
                    _events.get_events_since, project_id, cur_id, 100
                )
                for ev in events:
                    cur_id = ev["id"]
                    yield {
                        "event": ev["type"],
                        "data": _json.dumps(ev, default=str),
                    }
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(event_generator())


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


# === Cost-Endpoint (aggregiert, war in v1 mit JSON-Parsing) ===
@app.get("/api/cost/summary")
async def cost_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aggregierte Token/Cost-Stats der letzten N Tage (default 30).

    SQL-Aggregation (deutlich schneller als v1's JSON-Session-Parsing).
    Liefert: total, by_model, by_provider, by_role, by_day, savings.
    """
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    # Total
    totals = db.execute(
        select(
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_in), 0),
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_out), 0),
            sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0),
            sqlfunc.count(TokenUsage.id),
        ).where(TokenUsage.recorded_at >= cutoff)
    ).one()
    # By model
    by_model = db.execute(
        select(
            TokenUsage.model,
            sqlfunc.sum(TokenUsage.tokens_in),
            sqlfunc.sum(TokenUsage.tokens_out),
            sqlfunc.sum(TokenUsage.cost_usd),
            sqlfunc.count(TokenUsage.id),
        ).where(TokenUsage.recorded_at >= cutoff)
        .group_by(TokenUsage.model)
    ).all()
    # By provider
    by_provider = db.execute(
        select(
            TokenUsage.provider,
            sqlfunc.sum(TokenUsage.cost_usd),
            sqlfunc.count(TokenUsage.id),
        ).where(TokenUsage.recorded_at >= cutoff)
        .group_by(TokenUsage.provider)
    ).all()
    # By role
    by_role = db.execute(
        select(
            TokenUsage.role,
            sqlfunc.sum(TokenUsage.cost_usd),
            sqlfunc.count(TokenUsage.id),
        ).where(TokenUsage.recorded_at >= cutoff)
        .group_by(TokenUsage.role)
    ).all()
    # By day
    by_day_rows = db.execute(
        select(
            sqlfunc.strftime("%Y-%m-%d", TokenUsage.recorded_at).label("day"),
            sqlfunc.sum(TokenUsage.tokens_in),
            sqlfunc.sum(TokenUsage.tokens_out),
            sqlfunc.sum(TokenUsage.cost_usd),
        ).where(TokenUsage.recorded_at >= cutoff)
        .group_by("day")
        .order_by("day")
    ).all()
    return {
        "days": days,
        "total": {
            "tokens_in": int(totals[0]),
            "tokens_out": int(totals[1]),
            "cost_usd": float(totals[2]),
            "calls": int(totals[3]),
        },
        "by_model": [
            {"model": r[0], "tokens_in": int(r[1]), "tokens_out": int(r[2]),
             "cost_usd": float(r[3]), "calls": int(r[4])}
            for r in by_model
        ],
        "by_provider": [
            {"provider": r[0], "cost_usd": float(r[1]), "calls": int(r[2])}
            for r in by_provider
        ],
        "by_role": [
            {"role": r[0] or "unknown", "cost_usd": float(r[1]), "calls": int(r[2])}
            for r in by_role
        ],
        "by_day": [
            {"day": r[0], "tokens_in": int(r[1]), "tokens_out": int(r[2]), "cost_usd": float(r[3])}
            for r in by_day_rows
        ],
    }


# === Backup-Endpoint (SQLite .backup API) ===
@app.post("/api/kanban/backup")
async def create_backup(
    target_path: str = "database/pi_dashboard.backup.db",
    _user: str = Depends(require_auth),
):
    """Erstellt einen SQLite-Hot-Backup via sqlite3 .backup()-API.

    Format: Standard-SQLite-File, mit allen Tabellen, Indizes, Daten.
    Ziel: ./database/pi_dashboard.backup.db (oder custom path).
    """
    import sqlite3
    from pathlib import Path
    # Aktuelle DB-Connection
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    src = sqlite3.connect(db_path)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(str(target))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    size_mb = target.stat().st_size / (1024 * 1024)
    return {
        "ok": True,
        "path": str(target),
        "size_mb": round(size_mb, 3),
        "created_at": datetime.utcnow().isoformat(),
    }


# === Restore-Endpoint (ueberschreibt aktuelle DB) ===
@app.post("/api/kanban/restore")
async def restore_backup(
    source_path: str = "database/pi_dashboard.backup.db",
    confirm: bool = False,
    _user: str = Depends(require_auth),
):
    """Stellt einen SQLite-Backup wieder her.

    ACHTUNG: ueberschreibt die aktuelle DB! Nur mit confirm=true.
    """
    if not confirm:
        return {"ok": False, "error": "confirm=true erforderlich (DESTRUKTIVE OPERATION)"}
    from pathlib import Path
    src = Path(source_path)
    if not src.exists():
        raise HTTPException(404, f"Backup-File nicht gefunden: {source_path}")
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    import shutil
    shutil.copy2(str(src), db_path)
    return {
        "ok": True,
        "restored_from": str(src),
        "restored_to": db_path,
        "size_mb": round(src.stat().st_size / (1024 * 1024), 3),
        "restored_at": datetime.utcnow().isoformat(),
    }
