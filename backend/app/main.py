"""Pi Dashboard 2.0 — FastAPI Main-App.

v2.0-rc: Vollstaendige Router + Analytics + Index-Audit
Alle Daten werden in SQL gespeichert (SQLite/PostgreSQL via SQLAlchemy 2.0).
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, select, func as sqlfunc
from sqlalchemy.orm import Session

from .config import settings, BACKEND_ROOT
from .db.base import init_db, engine, SessionLocal, get_db
from .mcp_bus import MCPServer
from .auth import require_auth, require_role
from .schemas.error import ErrorResponse
from .utils.exceptions import DashboardError
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

_mcp_server: Optional[MCPServer] = None

# JSON-Logging Setup (Production-Ready) — toggle via LOG_FORMAT=json
import os
if os.getenv("LOG_FORMAT", "text").lower() == "json":
    import json
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
    for h in logging.root.handlers:
        h.setFormatter(JsonFormatter())


def _read_models_json() -> Dict[str, Any]:
    """Liest die zentrale models.json (Provider/Modell-Konfiguration)."""
    from .config import get_models_json_path

    p = get_models_json_path()
    if not p.exists():
        return {"providers": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"models.json read failed: {e}")
        return {"providers": {}}


def _read_auth_json() -> Dict[str, Any]:
    """Liest die zentrale auth.json (API-Keys)."""
    from .config import get_auth_json_path

    p = get_auth_json_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"auth.json read failed: {e}")
        return {}


def _check_provider_key_configured(provider: str) -> bool:
    """Prueft, ob fuer einen Provider ein API-Key vorhanden ist.

    Reihenfolge:
      1. ENV-Variable (z.B. KIMI_API_KEY, MINIMAX_API_KEY)
      2. auth.json Eintrag fuer den Provider
      3. apiKey/apiKeyRef in models.json
    """
    cfg = _read_models_json()
    prov_cfg = (cfg.get("providers") or {}).get(provider, {})
    if prov_cfg.get("apiKey") or prov_cfg.get("authHeader"):
        return True

    # ENV-Mapping
    env_var_map = {
        "kimi": "KIMI_API_KEY",
        "minimax-direct": "MINIMAX_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": "",  # kein Key noetig
    }
    env_var = env_var_map.get(provider, f"{provider.upper().replace('-', '_')}_API_KEY")
    if env_var and os.environ.get(env_var):
        return True

    auth = _read_auth_json()
    if isinstance(auth, dict) and provider in auth:
        entry = auth[provider]
        if isinstance(entry, dict) and entry.get("key"):
            return True
        if isinstance(entry, str) and entry:
            return True
    return False


def _validate_code_agent_provider() -> Dict[str, Any]:
    """Validiert die Sub-Agent Provider/Model-Konfiguration beim Start.

    Gibt ein Dict mit provider, model, valid, fallback, warnings zurueck.
    """
    from .services.worker_service import (
        CODE_AGENT_PROVIDER, CODE_AGENT_MODEL, _normalize_code_agent_provider_model,
    )

    provider, model = _normalize_code_agent_provider_model(
        CODE_AGENT_PROVIDER, CODE_AGENT_MODEL
    )
    cfg = _read_models_json()
    providers = cfg.get("providers") or {}
    warnings: list[str] = []
    fallback = False

    if provider not in providers:
        warnings.append(
            f"Sub-Agent Provider '{CODE_AGENT_PROVIDER}' nicht in models.json. "
            f"Fallback auf 'kimi'."
        )
        provider, model = "kimi", "kimi-k2.7-code"
        fallback = True

    prov_cfg = providers.get(provider, {})
    model_ids = {m.get("id") for m in prov_cfg.get("models", [])}
    if model not in model_ids:
        warnings.append(
            f"Sub-Agent Model '{model}' nicht fuer Provider '{provider}' in models.json. "
            f"Fallback auf 'kimi-k2.7-code'."
        )
        if "kimi-k2.7-code" in model_ids:
            model = "kimi-k2.7-code"
        elif model_ids:
            model = sorted(model_ids)[0]
        else:
            model = "kimi-k2.7-code"
            provider = "kimi"
        fallback = True

    key_ok = _check_provider_key_configured(provider)
    if not key_ok:
        warnings.append(
            f"Kein API-Key fuer Provider '{provider}' konfiguriert. "
            f"Bitte ENV-Variable oder auth.json setzen."
        )

    return {
        "provider": provider,
        "model": model,
        "valid": not fallback and key_ok,
        "fallback": fallback,
        "key_configured": key_ok,
        "warnings": warnings,
    }


def _alembic_is_current() -> bool:
    """Prueft, ob die Datenbank auf der neuesten Alembic-Revision ist.

    Gibt True zurueck, wenn Alembic nicht konfiguriert ist oder der
    aktuelle Head mit der Datenbank uebereinstimmt.
    """
    try:
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from alembic.config import Config

        alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(alembic_cfg)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            head_rev = script.get_current_head()
            return current_rev == head_rev
    except Exception as e:
        logger.warning(f"Could not verify Alembic revision: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App-Lifecycle: DB-Init + Role-Defaults beim Start."""
    logger.info("Pi Dashboard 2.0 starting...")
    logger.info(f"Database: {settings.DATABASE_URL}")
    # Sicherheits-Check: Auth erfordert sichere Secrets
    if settings.AUTH_ENABLED:
        if not settings.JWT_SECRET or settings.JWT_SECRET == "__CHANGE_ME__":
            raise RuntimeError(
                "AUTH_ENABLED=true, aber JWT_SECRET ist nicht gesetzt oder unsicher "
                "(Wert: __CHANGE_ME__). Bitte setze ein starkes JWT_SECRET in der .env."
            )
        if not settings.ADMIN_PASSWORD or settings.ADMIN_PASSWORD == "__CHANGE_ME__":
            raise RuntimeError(
                "AUTH_ENABLED=true, aber ADMIN_PASSWORD ist nicht gesetzt oder unsicher "
                "(Wert: __CHANGE_ME__). Bitte setze ein starkes ADMIN_PASSWORD in der .env."
            )
    try:
        if settings.ENV == "production":
            init_db()
            if not _alembic_is_current():
                logger.warning(
                    "Alembic is not at the latest revision. "
                    "Run 'alembic upgrade head' before running in production."
                )
            else:
                logger.info("Alembic version check passed.")
        else:
            init_db()
            logger.info("Development mode: Base.metadata.create_all() executed.")
        with SessionLocal() as db:
            added = RoleService.seed_defaults(db)
            if added:
                logger.info(f"Seeded {added} default roles.")
        # Sub-Agent Provider/Model validieren (User-Direktive: keine 401 durch Mismatch)
        try:
            code_agent_status = _validate_code_agent_provider()
            if code_agent_status["valid"]:
                logger.info(
                    f"Sub-Agent Provider-Validierung OK: {code_agent_status['provider']}/"
                    f"{code_agent_status['model']}"
                )
            else:
                logger.warning(
                    f"Sub-Agent Provider-Validierung: {code_agent_status['warnings']}"
                )
        except Exception as e:
            logger.warning(f"Sub-Agent Provider-Validierung fehlgeschlagen: {e}")
        # Session-IDs fuer die Background-Prozesse initialisieren
        try:
            from .services.session_helper import init_session_id
            init_session_id(force_type="server")
        except Exception as e:
            logger.warning(f"Session-ID-Init fehlgeschlagen: {e}")
        # Auto-Backup-Scheduler starten
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logger.warning(f"Backup-Scheduler konnte nicht starten: {e}")
        # Board-Operator-Watchdog starten (User-Direktive 17.06.2026)
        try:
            from .services.board_operator_service import start_watchdog
            await start_watchdog()
            logger.info("Board-Operator-Watchdog gestartet (Live-Mode-Handler)")
        except Exception as e:
            logger.warning(f"Board-Operator-Watchdog konnte nicht starten: {e}")
        # Worker-Loop starten (User-Direktive 17.06.2026: automatische Task-Bearbeitung)
        try:
            from .services.worker_loop import start_worker_loop
            await start_worker_loop()
            logger.info("Worker-Loop gestartet (automatische Task-Bearbeitung via LLM)")
        except Exception as e:
            logger.warning(f"Worker-Loop konnte nicht starten: {e}")
        # MCP-over-ZMQ Bus starten (User-Direktive: MCP/ZMQ Standard)
        global _mcp_server
        try:
            from . import mcp_tools  # noqa: F401 - registers tools
            from .mcp_tools import register_external_tools
            await register_external_tools()
            _mcp_server = MCPServer(session_factory=SessionLocal)
            await _mcp_server.start()
            logger.info(f"MCP-over-ZMQ server started with tools: {list(_mcp_server.tools().keys())}")
        except Exception as e:
            logger.warning(f"MCP-over-ZMQ server konnte nicht starten: {e}")
    except Exception as e:
        logger.error(f"Init failed: {e}")
        raise
    yield
    logger.info("Pi Dashboard 2.0 shutting down.")
    from .scheduler import stop_scheduler
    stop_scheduler()
    # Watchdog stoppen (alle Operator-Tasks)
    try:
        from .services.board_operator_service import stop_watchdog
        await stop_watchdog()
    except Exception as e:
        logger.warning(f"Watchdog-Stop fehlgeschlagen: {e}")
    # Worker-Loop stoppen
    try:
        from .services.worker_loop import stop_worker_loop
        await stop_worker_loop()
    except Exception as e:
        logger.warning(f"Worker-Loop-Stop fehlgeschlagen: {e}")
    # MCP-over-ZMQ Bus stoppen
    if _mcp_server is not None:
        try:
            await _mcp_server.stop()
            logger.info("MCP-over-ZMQ server stopped")
        except Exception as e:
            logger.warning(f"MCP-over-ZMQ server stop failed: {e}")
    engine.dispose()


app = FastAPI(
    title="Pi Dashboard 2.0",
    description="Hermes-Style Web-Dashboard fuer den lokalen PI Coding Agent — SQL-basiert",
    version="2.0.0-rc",
    lifespan=lifespan,
)


# === Globales Exception-Handling ===
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Einheitliche HTTP-Exception Responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse.from_exception(
            error="http_error",
            detail=str(exc.detail),
            status_code=exc.status_code,
        ).model_dump(),
    )


@app.exception_handler(DashboardError)
async def dashboard_exception_handler(request: Request, exc: DashboardError):
    """Wandelt bekannte Dashboard-Fehler in einheitliche Responses um."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse.from_exception(
            error=exc.__class__.__name__,
            detail=exc.message,
            status_code=exc.status_code,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fangt unerwartete Fehler und verhindert rohe Stacktraces im Response-Body."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.from_exception(
                error="http_error",
                detail=str(exc.detail),
                status_code=exc.status_code,
            ).model_dump(),
        )
    logger.error(f"Unerwarteter Fehler: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.from_exception(
            error="internal_error",
            detail="Ein unerwarteter Fehler ist aufgetreten",
            status_code=500,
        ).model_dump(),
    )


# CORS (Whitelist aus .env via CORS_ORIGINS env-var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate-Limiting (Production-Ready via slowapi)
if settings.RATE_LIMIT_PER_MINUTE > 0:  # type: ignore
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.errors import RateLimitExceeded
        from fastapi.responses import JSONResponse
        limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        logger.info(f"Rate-Limiting aktiviert: {settings.RATE_LIMIT_PER_MINUTE}/minute pro IP")
    except ImportError:
        logger.warning("slowapi nicht installiert, Rate-Limiting deaktiviert")

# === Routers ===
# Modul-Architektur: Jeder Router kapselt eine fachliche Domäne
# - projects/tasks/roles:    Kern-Domäne (Projekte, Tasks, Rollen)
# - models/roles:            LLM-Modell-Verwaltung + Berechtigungen
# - brainstorm/workflow:     Requirements-Engineering + State-Machine
# - selfimprovement/sops:    Meta-Governance (SOP-Engine, Self-Improve)
# - architecture_rules:      Standardvorgaben für Schritt 0
# - process_template:        BPMN-Templates für Task-Aggregation
# - agent_questions:         User<->Agent Interaktionstool
# - subagents:              SubAgent-Konfig
# - board_operators/test_runner: Live-Watchdog + Test-Navigator
from .routers import projects, tasks, models, roles, brainstorm, workflow, selfimprovement, transitions, sops, architecture_rules, process_template, agent_questions, board_operators, test_runner, subagents, tts, auth, provider_credentials, smproducer, swarm, swarm_events, ideas, subtasks, ports  # noqa: E402
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(models.router)
app.include_router(roles.router)
app.include_router(brainstorm.router)
app.include_router(workflow.router)
app.include_router(selfimprovement.router)
app.include_router(transitions.router)
app.include_router(sops.router)
app.include_router(process_template.router)
app.include_router(architecture_rules.router)  # User-Direktive 16.06.2026: Standardvorgaben für Schritt 0
app.include_router(agent_questions.router)  # User-Direktive 17.06.2026: User<->Agent Interaktionstool
app.include_router(subagents.router)  # User-Direktive 18.06.2026: SubAgent-Konfiguration (Modell pro Rolle)
app.include_router(board_operators.router)  # User-Direktive 17.06.2026: Live-Board Watchdog-Instanzen
app.include_router(test_runner.router)  # User-Direktive 17.06.2026: Navigator-Service fuer Test-Aktionen
app.include_router(swarm.router)  # User-Direktive 22.06.2026: Multi-Agent-Swarm (Phase 0-2)
app.include_router(swarm_events.router)  # Phase 14: SSE-Events für Live-Updates
app.include_router(ideas.router)  # Phase 19: Idee-Page CRUD
app.include_router(subtasks.router)  # Phase 20: Sub-Tasks mit Planung + Session-ID
app.include_router(ports.router)  # Task 4bf7146b0780: Port-Management
app.include_router(tts.router)  # MiniMax Text-to-Audio V2
app.include_router(auth.router)  # JWT Login
app.include_router(provider_credentials.router)  # Zentrale API-Key-Verwaltung
app.include_router(smproducer.router)  # OpenBrain-konforme SMproducer 3.0 Bridge


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
                           "implementation_steps", "event_log",
                           "agent_questions", "agent_question_attachments",
                           "board_operators"]
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
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/health/providers")
async def health_providers(
    _user: str = Depends(require_auth),
):
    """Provider-Health: Sub-Agent Config + Key-Status fuer alle konfigurierten Provider."""
    code_agent_status = _validate_code_agent_provider()
    cfg = _read_models_json()
    providers = cfg.get("providers") or {}
    provider_status = {}
    for name, prov_cfg in providers.items():
        model_ids = [m.get("id") for m in prov_cfg.get("models", [])]
        provider_status[name] = {
            "base_url": prov_cfg.get("baseUrl") or prov_cfg.get("api"),
            "models": model_ids,
            "supports_parallel": prov_cfg.get("supportsParallel", False),
            "key_configured": _check_provider_key_configured(name),
        }
    return {
        "status": "ok" if code_agent_status["valid"] else "degraded",
        "code_agent": code_agent_status,
        "providers": provider_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# Version-Lifecycle (Task aadf7b23d059):
#   v2.0.0-beta  →  v2.0.0-rc  →  v2.0.0-stable
# Aktuelle Phase: Release-Candidate (Index-Audit + Performance-Optimierung)
# Naechste Phase: Stable-Release mit v1-Migration + Production-Readiness
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
    _user: str = Depends(require_role("cio")),
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
                "ts": datetime.now(timezone.utc).isoformat(),
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
    _user: str = Depends(require_role("admin")),
):
    """Fuehrt ANALYZE auf der DB aus — sammelt sqlite_stat1 fuer EXPLAIN-Ausgaben."""
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()
    return {"ok": True, "message": "ANALYZE ausgefuehrt"}


@app.get("/api/analytics/index-usage")
async def index_usage(
    db: Session = Depends(get_db),
    _user: str = Depends(require_role("admin")),
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
    return {"indexes": out, "analyzed_at": datetime.now(timezone.utc).isoformat()}


# === Cost-Endpoint (aggregiert, war in v1 mit JSON-Parsing) ===
@app.get("/api/cost/summary")
async def cost_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: str = Depends(require_role("cio")),
):
    """Aggregierte Token/Cost-Stats der letzten N Tage (default 30).

    SQL-Aggregation (deutlich schneller als v1's JSON-Session-Parsing).
    Liefert: total, by_model, by_provider, by_role, by_day, savings.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
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
    _user: str = Depends(require_role("admin")),
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# === Restore-Endpoint (ueberschreibt aktuelle DB) ===
@app.post("/api/kanban/restore")
async def restore_backup(
    source_path: str = "database/pi_dashboard.backup.db",
    confirm: bool = False,
    _user: str = Depends(require_role("admin")),
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
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
