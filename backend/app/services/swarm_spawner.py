"""SwarmSpawner — Multi-Agent-Swarm-Orchestrator.

User-Direktive 22.06.2026: Staged Hybrid Swarm fuer SOP 7c86692be939.
Stages:
  #2 Implementation — 3 parallele pi-coder (minimalist/robust/performant)
  #3 Multi-Test    — 3 parallele pi-tester (unit/integration/performance)
  #4 Review        — 3 kompetitive Reviewer (quality/bugs/robustness)

Swarm-Typen:
  - single: 1 Worker (Triage, Planning, Final)
  - parallel: N Worker parallel, Merge via Konfiguration
  - competitive: N Worker, Konsens-Score, Auto-Approve bei Score >= Threshold

Merge-Strategien:
  - reviewer_picks_best: pi-reviewer bewertet und waehlt
  - merge_all: alle Outputs zusammenfuehren (Code-Merge, Test-Suite-Merge)
  - consensus_score: gewichteter Score-Durchschnitt
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pi-dashboard-2.swarm")


class SwarmType(str, Enum):
    SINGLE = "single"
    PARALLEL = "parallel"
    COMPETITIVE = "competitive"


class SwarmStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MergeStrategy(str, Enum):
    REVIEWER_PICKS_BEST = "reviewer_picks_best"
    MERGE_ALL = "merge_all"
    CONSENSUS_SCORE = "consensus_score"
    FIRST_SUCCESS = "first_success"


class WorkerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerConfig:
    role: str
    variant: str = "default"
    weight: float = 1.0
    system_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class WorkerResult:
    worker_id: str
    role: str
    variant: str
    status: WorkerStatus
    output: Optional[str] = None
    cost_usd: float = 0.0
    score: Optional[float] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class SwarmConfig:
    swarm_type: SwarmType
    workers: List[WorkerConfig]
    merge_strategy: MergeStrategy = MergeStrategy.REVIEWER_PICKS_BEST
    consensus_threshold: float = 75.0
    auto_approve_threshold: float = 90.0
    max_cost_usd: float = 0.50
    timeout_sec: int = 600
    use_real_workers: bool = False  # Phase 11: echte SubAgent-Calls statt Mock

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SwarmConfig":
        workers = [WorkerConfig(**w) for w in data.get("workers", [])]
        return cls(
            swarm_type=SwarmType(data.get("swarm_type", "parallel")),
            workers=workers,
            merge_strategy=MergeStrategy(data.get("merge_strategy", "reviewer_picks_best")),
            consensus_threshold=data.get("consensus_threshold", 75.0),
            auto_approve_threshold=data.get("auto_approve_threshold", 90.0),
            max_cost_usd=data.get("max_cost_usd", 0.50),
            timeout_sec=data.get("timeout_sec", 600),
            use_real_workers=bool(data.get("use_real_workers", False)),
        )


# === Default Swarm-Konfigurationen pro SOP-Stage ===

SWARM_CONFIGS = {
    "stage2_implementation": SwarmConfig(
        swarm_type=SwarmType.PARALLEL,
        workers=[
            WorkerConfig(role="pi-coder", variant="minimalist",
                         system_prompt="Minimaler, lesbarer Code. Keine Over-Engineering."),
            WorkerConfig(role="pi-coder", variant="robust",
                         system_prompt="Defensive Programmierung. Edge-Cases abdecken. Null-Checks."),
            WorkerConfig(role="pi-coder", variant="performant",
                         system_prompt="Performance-optimiert. O(n)-Analyse. Memory-Profiling."),
        ],
        merge_strategy=MergeStrategy.REVIEWER_PICKS_BEST,
        max_cost_usd=0.50,
    ),
    "stage3_multi_test": SwarmConfig(
        swarm_type=SwarmType.PARALLEL,
        workers=[
            WorkerConfig(role="pi-tester", variant="unit",
                         system_prompt="Unit-Tests schreiben. Coverage > 90%. Edge-Cases."),
            WorkerConfig(role="pi-tester", variant="integration",
                         system_prompt="Integration-Tests. API-Contracts. End-to-End-Flows."),
            WorkerConfig(role="pi-tester", variant="performance",
                         system_prompt="Performance-Tests. Load-Testing. Latenz-Messung."),
        ],
        merge_strategy=MergeStrategy.MERGE_ALL,
        max_cost_usd=0.30,
    ),
    "stage4_competitive_review": SwarmConfig(
        swarm_type=SwarmType.COMPETITIVE,
        workers=[
            WorkerConfig(role="pi-reviewer", variant="code-quality", weight=1.0,
                         system_prompt="Bewerte Code-Quality: Lesbarkeit, Patterns, Naming, DRY."),
            WorkerConfig(role="pi-tester", variant="bug-finding", weight=1.0,
                         system_prompt="Finde Bugs: Edge-Cases, Race-Conditions, Error-Handling."),
            WorkerConfig(role="pi-fixer", variant="robustness", weight=1.0,
                         system_prompt="Pruefe Robustheit: Input-Validierung, Failure-Modes, Recovery."),
        ],
        merge_strategy=MergeStrategy.CONSENSUS_SCORE,
        consensus_threshold=75.0,
        auto_approve_threshold=90.0,
        max_cost_usd=0.20,
    ),
}


# === Datenbank-Operationen ===

def _get_conn() -> sqlite3.Connection:
    """Lazy-Connect zur DB. Konfiguration via env PI_DB_PATH."""
    import os
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    return sqlite3.connect(db_path)


def _ensure_swarm_tables() -> None:
    """Stellt sicher, dass swarm_runs und swarm_workers existieren.

    Idempotent: nutzt CREATE TABLE IF NOT EXISTS.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS swarm_runs (
            id VARCHAR(32) PRIMARY KEY,
            task_id VARCHAR(32),
            sop_instance_id VARCHAR(32),
            step_id VARCHAR(32),
            swarm_type VARCHAR(32) NOT NULL,
            workers_config TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            merge_strategy VARCHAR(32),
            consensus_threshold FLOAT DEFAULT 75.0,
            auto_approve_threshold FLOAT DEFAULT 90.0,
            result TEXT,
            total_cost_usd FLOAT DEFAULT 0.0,
            started_at DATETIME,
            completed_at DATETIME
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS swarm_workers (
            id VARCHAR(32) PRIMARY KEY,
            swarm_run_id VARCHAR(32) NOT NULL,
            subagent_role VARCHAR(64) NOT NULL,
            variant VARCHAR(64),
            weight FLOAT DEFAULT 1.0,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            output TEXT,
            cost_usd FLOAT DEFAULT 0.0,
            score FLOAT,
            error TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY (swarm_run_id) REFERENCES swarm_runs(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_task ON swarm_runs(task_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_swarm_workers_run ON swarm_workers(swarm_run_id)")
    conn.commit()
    conn.close()


def create_swarm_run(
    task_id: str,
    sop_instance_id: str,
    step_id: str,
    config: SwarmConfig,
) -> str:
    """Legt einen neuen Swarm-Run in der DB an. Gibt swarm_run_id zurueck."""
    _ensure_swarm_tables()
    swarm_id = f"swarm-{secrets.token_hex(6)}"
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO swarm_runs
        (id, task_id, sop_instance_id, step_id, swarm_type, workers_config,
         status, merge_strategy, consensus_threshold, auto_approve_threshold)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        swarm_id, task_id, sop_instance_id, step_id,
        config.swarm_type.value,
        json.dumps([w.to_dict() for w in config.workers]),
        SwarmStatus.PENDING.value,
        config.merge_strategy.value,
        config.consensus_threshold,
        config.auto_approve_threshold,
    ))
    for w in config.workers:
        cur.execute("""
            INSERT INTO swarm_workers
            (id, swarm_run_id, subagent_role, variant, weight, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (f"w-{secrets.token_hex(6)}", swarm_id, w.role, w.variant, w.weight,
              WorkerStatus.PENDING.value))
    conn.commit()
    conn.close()
    logger.info(f"Swarm-Run erstellt: {swarm_id} (type={config.swarm_type.value}, "
                f"workers={len(config.workers)}, task={task_id})")
    return swarm_id


def update_swarm_status(swarm_id: str, status: SwarmStatus,
                         result: Optional[Dict[str, Any]] = None,
                         total_cost_usd: Optional[float] = None) -> None:
    """Updated Status + optional Result + Cost eines Swarm-Runs."""
    conn = _get_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if status in (SwarmStatus.COMPLETED, SwarmStatus.FAILED):
        cur.execute("""
            UPDATE swarm_runs SET status = ?, result = ?, total_cost_usd = ?, completed_at = ?
            WHERE id = ?
        """, (status.value, json.dumps(result) if result else None,
              total_cost_usd if total_cost_usd is not None else 0.0,
              now, swarm_id))
    else:
        cur.execute("""
            UPDATE swarm_runs SET status = ?, started_at = COALESCE(started_at, ?)
            WHERE id = ?
        """, (status.value, now, swarm_id))
    conn.commit()
    conn.close()


def update_worker_status(worker_id: str, status: WorkerStatus,
                          output: Optional[str] = None,
                          cost_usd: Optional[float] = None,
                          score: Optional[float] = None,
                          error: Optional[str] = None) -> None:
    """Updated einen Worker-Status."""
    conn = _get_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    fields = ["status = ?"]
    values: List[Any] = [status.value]
    if output is not None:
        fields.append("output = ?")
        values.append(output)
    if cost_usd is not None:
        fields.append("cost_usd = ?")
        values.append(cost_usd)
    if score is not None:
        fields.append("score = ?")
        values.append(score)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if status in (WorkerStatus.COMPLETED, WorkerStatus.FAILED):
        fields.append("completed_at = ?")
        values.append(now)
    elif status == WorkerStatus.RUNNING:
        fields.append("started_at = COALESCE(started_at, ?)")
        values.append(now)
    values.append(worker_id)
    cur.execute(f"UPDATE swarm_workers SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_swarm_run(swarm_id: str) -> Optional[Dict[str, Any]]:
    """Liefert Swarm-Run + alle Worker."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM swarm_runs WHERE id = ?", (swarm_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cols = [d[0] for d in cur.description]
    run = dict(zip(cols, row))
    cur.execute("SELECT * FROM swarm_workers WHERE swarm_run_id = ?", (swarm_id,))
    w_cols = [d[0] for d in cur.description]
    run["workers"] = [dict(zip(w_cols, w)) for w in cur.fetchall()]
    conn.close()
    return run


# === Mock-Worker-Execution (fuer Tests und Dev) ===

async def execute_worker_mock(
    worker_role: str,
    variant: str,
    task_context: Dict[str, Any],
    timeout_sec: int = 600,
) -> WorkerResult:
    """Mock-Worker: simuliert einen Worker-Output.

    In Produktion wird dies durch den echten subagent_service ersetzt.
    """
    worker_id = f"w-{secrets.token_hex(4)}"
    logger.info(f"Mock-Worker {worker_role}/{variant} startet (id={worker_id})")
    await asyncio.sleep(0.05)  # Simulierte Arbeit
    output = json.dumps({
        "role": worker_role,
        "variant": variant,
        "approach": f"Mock-Ansatz fuer {variant}",
        "code": f"# Code von {worker_role}/{variant}\npass",
        "rationale": f"Dies ist ein Mock-Output fuer Tests. Variante: {variant}",
    })
    return WorkerResult(
        worker_id=worker_id,
        role=worker_role,
        variant=variant,
        status=WorkerStatus.COMPLETED,
        output=output,
        cost_usd=0.05,  # Mock-Kosten
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


# === Echte Worker-Execution (Phase 11) ===

import os
import signal
import subprocess
import time as _time
from pathlib import Path


def _is_process_alive(pid: int) -> bool:
    """Prueft ob ein Prozess mit der PID noch laeuft (Windows + Unix)."""
    if pid is None or pid <= 0:
        return False
    try:
        if os.name == "nt":
            # Windows: kein os.kill, stattdessen subprocess oder tasklist
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            return str(pid) in stdout or str(pid) in stderr
        else:
            # Unix: os.kill(pid, 0) testet Existenz ohne Signal
            os.kill(pid, 0)
            return True
    except (subprocess.TimeoutExpired, OSError, ProcessLookupError):
        return False


def _tail_log(log_path: str, max_lines: int = 100) -> str:
    """Liest die letzten N Zeilen einer Log-Datei."""
    try:
        p = Path(log_path)
        if not p.exists():
            return ""
        # Performance: nur letzte 64KB lesen
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > 65536:
                f.seek(size - 65536)
            content = f.read().decode("utf-8", errors="replace")
        lines = content.splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        logger.warning(f"Konnte Log nicht lesen: {e}")
        return ""


async def execute_worker_real(
    worker_role: str,
    variant: str,
    task_context: Dict[str, Any],
    timeout_sec: int = 600,
) -> WorkerResult:
    """Echter Worker: spawnt SubAgent und wartet auf Output.

    User-Direktive 22.06.2026 Phase 11: Echte Worker statt Mock.
    Strategie:
      1. SubAgent-Prozess via subagent_service.spawn_sub_agent() starten
      2. Polling auf Process-Exit (alle 5s, max timeout_sec)
      3. Output aus Log-Datei extrahieren
      4. Bei Timeout: Worker als 'failed' markieren, Process killen

    Args:
        worker_role: z.B. 'pi-coder', 'pi-tester', 'pi-reviewer'
        variant: z.B. 'minimalist', 'robust', 'quality'
        task_context: Dict mit task_id, title, description, etc.
        timeout_sec: Max Wartezeit

    Returns:
        WorkerResult mit output, cost_usd, status
    """
    worker_id = f"w-{secrets.token_hex(4)}"
    started_at = datetime.now(timezone.utc).isoformat()

    # Task laden (falls nur ID vorhanden)
    task_id = task_context.get("task_id")
    if not task_id:
        return WorkerResult(
            worker_id=worker_id, role=worker_role, variant=variant,
            status=WorkerStatus.FAILED, error="task_id fehlt in task_context",
            started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
        )

    # SubAgent spawnen
    try:
        from app.services.sub_agent import spawn_sub_agent
        from app.db.base import SessionLocal
        from app.models.task import Task

        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if not task:
                return WorkerResult(
                    worker_id=worker_id, role=worker_role, variant=variant,
                    status=WorkerStatus.FAILED, error=f"Task {task_id} nicht gefunden",
                    started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
                )

            # System-Prompt mit Variant-Info erweitern (User-Direktive 24.06.2026):
            # Worker-Prompts kommen aus dem SOP-Step (WorkerConfig.system_prompt) oder
            # aus den Rollen-Definitionen (role.system_prompt + variant-Anweisung).
            # NICHT mehr hardcoded in swarm_spawner.py.
            if task.meta is None:
                task.meta = {}
            if not task.meta.get("variant_prompt"):
                # Hole Worker-Prompt aus dem SOP-Context (von der SOP-Engine gesetzt)
                variant_prompt = task_context.get("worker_prompts", {}).get(
                    f"{worker_role}:{variant}", ""
                ) or task_context.get("worker_prompts", {}).get(worker_role, "")
                if variant_prompt:
                    task.meta["variant_prompt"] = variant_prompt
                else:
                    # Letzter Fallback: Rollen-System-Prompt (aus roles-Tabelle)
                    from app.models.role import Role
                    from sqlalchemy import select
                    role = db.execute(
                        select(Role).where(Role.name == worker_role)
                    ).scalar_one_or_none()
                    if role and role.system_prompt:
                        task.meta["variant_prompt"] = (
                            f"## VARIANTE: {variant}\n"
                            f"Setze die oben beschriebene Persona um unter Beruecksichtigung "
                            f"der Variante '{variant}'.\n\n"
                            f"### ROLLE\n{role.system_prompt}"
                        )
            # assigned_subagent setzen damit spawn_sub_agent ihn nimmt
            task.assigned_subagent = worker_role
            db.commit()

            spawn_result = await spawn_sub_agent(task, db)
        finally:
            db.close()
    except Exception as e:
        logger.exception(f"SubAgent-Spawn fehlgeschlagen: {e}")
        return WorkerResult(
            worker_id=worker_id, role=worker_role, variant=variant,
            status=WorkerStatus.FAILED, error=f"Spawn-Fehler: {e}",
            started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
        )

    if not spawn_result:
        return WorkerResult(
            worker_id=worker_id, role=worker_role, variant=variant,
            status=WorkerStatus.FAILED, error="Spawn lieferte None",
            started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
        )

    pid = spawn_result.get("pid")
    log_path = spawn_result.get("log_path")
    logger.info(f"Worker {worker_id} ({worker_role}/{variant}) gestartet: PID={pid}, Log={log_path}")

    # Polling auf Process-Exit
    poll_interval = 5  # Sekunden
    max_wait = timeout_sec
    waited = 0
    while waited < max_wait:
        if not _is_process_alive(pid):
            break
        await asyncio.sleep(poll_interval)
        waited += poll_interval
        if waited % 30 == 0:
            logger.info(f"Worker {worker_id} laeuft seit {waited}s...")

    # Timeout-Check
    if _is_process_alive(pid):
        logger.warning(f"Worker {worker_id} hat Timeout nach {max_wait}s, kille PID {pid}")
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception as e:
            logger.error(f"Process-Kill fehlgeschlagen: {e}")
        return WorkerResult(
            worker_id=worker_id, role=worker_role, variant=variant,
            status=WorkerStatus.FAILED, error=f"Timeout nach {max_wait}s",
            started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat(),
        )

    # Output extrahieren
    output_text = _tail_log(log_path, max_lines=200) if log_path else ""
    completed_at = datetime.now(timezone.utc).isoformat()

    # Kosten aus token_usage extrahieren (falls vorhanden)
    cost_usd = 0.0
    try:
        from app.db.base import SessionLocal
        from app.models.token_usage import TokenUsage
        db = SessionLocal()
        try:
            usages = db.query(TokenUsage).filter_by(task_id=task_id).all()
            cost_usd = sum(float(u.cost_usd or 0) for u in usages)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Konnte TokenUsage nicht laden: {e}")

    return WorkerResult(
        worker_id=worker_id,
        role=worker_role,
        variant=variant,
        status=WorkerStatus.COMPLETED,
        output=output_text,
        cost_usd=cost_usd,
        started_at=started_at,
        completed_at=completed_at,
    )


async def execute_swarm(swarm_id: str, task_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Orchestriert einen kompletten Swarm-Run.

    1. Laedt Config
    2. Startet alle Worker (parallel oder single)
    3. Wartet auf alle
    4. Wendet Merge-Strategie an
    5. Liefert Ergebnis
    """
    task_context = task_context or {}
    run = get_swarm_run(swarm_id)
    if not run:
        raise ValueError(f"Swarm-Run {swarm_id} nicht gefunden")

    update_swarm_status(swarm_id, SwarmStatus.RUNNING)
    logger.info(f"Swarm {swarm_id} startet ({run['swarm_type']}, {len(run['workers'])} Worker)")

    workers = run["workers"]
    results: List[WorkerResult] = []

    # Worker-Executor waehlen (Phase 11)
    # use_real_workers wird als ENV ueberschrieben (PI_SWARM_USE_REAL=1) ODER aus DB
    use_real_env = os.environ.get("PI_SWARM_USE_REAL", "").lower() in ("1", "true", "yes")
    workers_cfg_raw = run.get("workers_config", "{}")
    try:
        workers_cfg = json.loads(workers_cfg_raw) if isinstance(workers_cfg_raw, str) else workers_cfg_raw
    except (json.JSONDecodeError, TypeError):
        workers_cfg = {}
    # SwarmConfig optional erweitert: use_real_workers aus workers_cfg
    use_real_db = bool(workers_cfg.get("use_real_workers", False)) if isinstance(workers_cfg, dict) else False
    use_real = use_real_env or use_real_db
    worker_fn = execute_worker_real if use_real else execute_worker_mock
    if use_real:
        logger.info(f"Swarm {swarm_id} verwendet ECHTE Worker (Phase 11)")

    # SwarmConfig aus DB-Daten rekonstruieren (fuer timeout_sec etc.)
    try:
        config = SwarmConfig(
            swarm_type=SwarmType(run["swarm_type"]),
            workers=[WorkerConfig(**w) for w in workers_cfg.get("workers", [])] if isinstance(workers_cfg, dict) else [],
            merge_strategy=MergeStrategy(run.get("merge_strategy") or "reviewer_picks_best"),
            consensus_threshold=float(run.get("consensus_threshold") or 75.0),
            auto_approve_threshold=float(run.get("auto_approve_threshold") or 90.0),
            max_cost_usd=float(run.get("max_cost_usd") or 0.50),
            timeout_sec=int(run.get("timeout_sec") or 600),
            use_real_workers=use_real,
        )
    except Exception:
        config = None

    try:
        if run["swarm_type"] == SwarmType.SINGLE.value:
            # Single-Mode: nur der erste Worker
            w = workers[0]
            update_worker_status(w["id"], WorkerStatus.RUNNING)
            result = await worker_fn(w["subagent_role"], w.get("variant") or "default", task_context,
                                     timeout_sec=config.timeout_sec)
            update_worker_status(w["id"], result.status, output=result.output, cost_usd=result.cost_usd)
            results.append(result)
        else:
            # Parallel-Mode: alle gleichzeitig
            tasks = []
            for w in workers:
                update_worker_status(w["id"], WorkerStatus.RUNNING)
                tasks.append(worker_fn(
                    w["subagent_role"], w.get("variant") or "default", task_context,
                    timeout_sec=config.timeout_sec,
                ))
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for w, r in zip(workers, results):
                update_worker_status(w["id"], r.status, output=r.output, cost_usd=r.cost_usd)

        # Merge-Strategie anwenden
        merge_strategy = MergeStrategy(run["merge_strategy"])
        merged = _apply_merge_strategy(results, merge_strategy)

        total_cost = sum(r.cost_usd for r in results)
        result_payload = {
            "merged_output": merged,
            "worker_count": len(results),
            "total_cost_usd": total_cost,
            "merge_strategy": merge_strategy.value,
        }
        update_swarm_status(swarm_id, SwarmStatus.COMPLETED,
                            result=result_payload, total_cost_usd=total_cost)
        logger.info(f"Swarm {swarm_id} abgeschlossen. Cost=${total_cost:.2f}")
        return result_payload

    except Exception as e:
        logger.exception(f"Swarm {swarm_id} fehlgeschlagen: {e}")
        update_swarm_status(swarm_id, SwarmStatus.FAILED, result={"error": str(e)})
        raise


def _apply_merge_strategy(results: List[WorkerResult], strategy: MergeStrategy) -> Dict[str, Any]:
    """Wendet die konfigurierte Merge-Strategie auf die Worker-Outputs an."""
    if strategy == MergeStrategy.REVIEWER_PICKS_BEST:
        # Mock: erstes Completed-Worker-Output als "best"
        # In Produktion: pi-reviewer bewertet und waehlt
        for r in results:
            if r.status == WorkerStatus.COMPLETED and r.output:
                return {"strategy": "reviewer_picks_best", "winner": r.role + "/" + r.variant,
                        "output": r.output}
        return {"strategy": "reviewer_picks_best", "winner": None, "output": None}

    elif strategy == MergeStrategy.MERGE_ALL:
        # Mock: alle Outputs konkatenieren
        return {"strategy": "merge_all", "outputs": [r.output for r in results if r.output]}

    elif strategy == MergeStrategy.CONSENSUS_SCORE:
        # Mock: gleicher Score fuer alle (in Produktion: pi-reviewer bewertet)
        scores = [85.0 for _ in results]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {"strategy": "consensus_score", "scores": scores, "avg_score": avg_score,
                "auto_approve": avg_score >= 90.0}

    elif strategy == MergeStrategy.FIRST_SUCCESS:
        for r in results:
            if r.status == WorkerStatus.COMPLETED:
                return {"strategy": "first_success", "output": r.output}

    return {"strategy": strategy.value, "results_count": len(results)}