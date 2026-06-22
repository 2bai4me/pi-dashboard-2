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
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
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

    try:
        if run["swarm_type"] == SwarmType.SINGLE.value:
            # Single-Mode: nur der erste Worker
            w = workers[0]
            update_worker_status(w["id"], WorkerStatus.RUNNING)
            result = await execute_worker_mock(w["subagent_role"], w.get("variant") or "default", task_context)
            update_worker_status(w["id"], result.status, output=result.output, cost_usd=result.cost_usd)
            results.append(result)
        else:
            # Parallel-Mode: alle gleichzeitig
            tasks = []
            for w in workers:
                update_worker_status(w["id"], WorkerStatus.RUNNING)
                tasks.append(execute_worker_mock(
                    w["subagent_role"], w.get("variant") or "default", task_context
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