"""Tests fuer SwarmSpawner (Staged Hybrid Multi-Agent).

User-Direktive 22.06.2026: Vollautomatischer Prozess mit Multi-Agent-Swarm.
Diese Tests sichern die Kernlogik des Swarm-Spawners ab.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# Test-DB in temp-Verzeichnis anlegen
@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_pi.db"
    monkeypatch.setenv("PI_DB_PATH", str(db_path))
    # FIX 23.06.2026 (Task b2155f9cae64, pi-fixer):
    # PI_SWARM_USE_REAL ist in der globalen Shell-Umgebung auf "1" gesetzt
    # (Production-Mode "Phase 11 = echte Worker"). In Tests wuerde das den
    # Mock-Worker ueberschreiben, sodass execute_worker_real versucht
    # SubAgents zu spawnen - was ohne DB/SubagentService fehlschlaegt.
    # Tests muessen daher explizit Mock-Workers erzwingen.
    monkeypatch.delenv("PI_SWARM_USE_REAL", raising=False)
    monkeypatch.setenv("PI_SWARM_USE_REAL", "0")
    # Schema minimal erstellen (nur swarm_runs + swarm_workers werden benoetigt)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE swarm_runs (
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
    conn.execute("""
        CREATE TABLE swarm_workers (
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
    conn.commit()
    conn.close()
    yield str(db_path)


def test_create_swarm_run_creates_run_and_workers(temp_db):
    from app.services.swarm_spawner import (
        SwarmConfig, WorkerConfig, SwarmType, MergeStrategy, create_swarm_run, get_swarm_run
    )
    config = SwarmConfig(
        swarm_type=SwarmType.PARALLEL,
        workers=[
            WorkerConfig(role="pi-coder", variant="minimalist"),
            WorkerConfig(role="pi-coder", variant="robust"),
            WorkerConfig(role="pi-coder", variant="performant"),
        ],
        merge_strategy=MergeStrategy.REVIEWER_PICKS_BEST,
        max_cost_usd=0.50,
    )
    swarm_id = create_swarm_run("task-1", "inst-1", "step-1", config)
    assert swarm_id.startswith("swarm-")
    run = get_swarm_run(swarm_id)
    assert run is not None
    assert run["status"] == "pending"
    assert run["swarm_type"] == "parallel"
    assert len(run["workers"]) == 3
    assert {w["variant"] for w in run["workers"]} == {"minimalist", "robust", "performant"}


def test_swarm_config_from_dict():
    from app.services.swarm_spawner import SwarmConfig, SwarmType, MergeStrategy
    data = {
        "swarm_type": "parallel",
        "workers": [
            {"role": "pi-coder", "variant": "minimalist"},
            {"role": "pi-coder", "variant": "robust"},
        ],
        "merge_strategy": "reviewer_picks_best",
        "max_cost_usd": 0.5,
    }
    config = SwarmConfig.from_dict(data)
    assert config.swarm_type == SwarmType.PARALLEL
    assert len(config.workers) == 2
    assert config.merge_strategy == MergeStrategy.REVIEWER_PICKS_BEST
    assert config.max_cost_usd == 0.5


def test_execute_swarm_parallel(temp_db):
    """Smoke-Test: Paralleler Swarm laeuft durch und liefert Ergebnis."""
    from app.services.swarm_spawner import (
        SwarmConfig, WorkerConfig, SwarmType, MergeStrategy,
        create_swarm_run, execute_swarm, get_swarm_run
    )
    config = SwarmConfig(
        swarm_type=SwarmType.PARALLEL,
        workers=[
            WorkerConfig(role="pi-coder", variant="minimalist"),
            WorkerConfig(role="pi-coder", variant="robust"),
            WorkerConfig(role="pi-coder", variant="performant"),
        ],
        merge_strategy=MergeStrategy.REVIEWER_PICKS_BEST,
    )
    swarm_id = create_swarm_run("task-1", "inst-1", "step-2", config)
    result = asyncio.run(execute_swarm(swarm_id, task_context={"title": "Test"}))
    assert result["worker_count"] == 3
    assert "merged_output" in result
    assert result["total_cost_usd"] > 0
    run = get_swarm_run(swarm_id)
    assert run["status"] == "completed"
    assert all(w["status"] == "completed" for w in run["workers"])


def test_execute_swarm_single(temp_db):
    """Single-Swarm: nur 1 Worker wird ausgefuehrt."""
    from app.services.swarm_spawner import (
        SwarmConfig, WorkerConfig, SwarmType,
        create_swarm_run, execute_swarm, get_swarm_run
    )
    config = SwarmConfig(
        swarm_type=SwarmType.SINGLE,
        workers=[WorkerConfig(role="pi-architect", variant="default")],
    )
    swarm_id = create_swarm_run("task-2", "inst-2", "step-1", config)
    result = asyncio.run(execute_swarm(swarm_id))
    assert result["worker_count"] == 1
    run = get_swarm_run(swarm_id)
    assert all(w["status"] == "completed" for w in run["workers"])


def test_execute_swarm_competitive_with_consensus(temp_db):
    """Competitive Swarm: Konsens-Score wird berechnet (Mock: 85), Auto-Approve < 90."""
    from app.services.swarm_spawner import (
        SwarmConfig, WorkerConfig, SwarmType, MergeStrategy,
        create_swarm_run, execute_swarm
    )
    config = SwarmConfig(
        swarm_type=SwarmType.COMPETITIVE,
        workers=[
            WorkerConfig(role="pi-reviewer", variant="quality"),
            WorkerConfig(role="pi-tester", variant="bugs"),
            WorkerConfig(role="pi-fixer", variant="robustness"),
        ],
        merge_strategy=MergeStrategy.CONSENSUS_SCORE,
        auto_approve_threshold=90.0,
    )
    swarm_id = create_swarm_run("task-3", "inst-3", "step-4", config)
    result = asyncio.run(execute_swarm(swarm_id))
    assert "merged_output" in result
    merged = result["merged_output"]
    assert "scores" in merged
    assert "avg_score" in merged
    assert merged["strategy"] == "consensus_score"
    # Mock-Score ist 85 -> unter Threshold 90 -> kein Auto-Approve
    assert merged["auto_approve"] is False
    assert merged["avg_score"] == 85.0


def test_swarm_persists_total_cost(temp_db):
    """Die Gesamtkosten des Swarms werden in der DB persistiert."""
    from app.services.swarm_spawner import (
        SwarmConfig, WorkerConfig, SwarmType,
        create_swarm_run, execute_swarm, get_swarm_run
    )
    config = SwarmConfig(
        swarm_type=SwarmType.PARALLEL,
        workers=[
            WorkerConfig(role="pi-coder", variant="a"),
            WorkerConfig(role="pi-coder", variant="b"),
        ],
    )
    swarm_id = create_swarm_run("task-cost", "inst-cost", "step-cost", config)
    result = asyncio.run(execute_swarm(swarm_id))
    run = get_swarm_run(swarm_id)
    assert run["total_cost_usd"] == result["total_cost_usd"]
    assert run["total_cost_usd"] > 0


def test_default_configs_for_all_stages():
    """Alle 3 Stufen (Implementation, Test, Review) haben Default-Konfigs."""
    from app.services.swarm_spawner import SWARM_CONFIGS
    assert "stage2_implementation" in SWARM_CONFIGS
    assert "stage3_multi_test" in SWARM_CONFIGS
    assert "stage4_competitive_review" in SWARM_CONFIGS
    impl = SWARM_CONFIGS["stage2_implementation"]
    assert len(impl.workers) == 3
    assert all(w.role == "pi-coder" for w in impl.workers)
    review = SWARM_CONFIGS["stage4_competitive_review"]
    assert review.swarm_type.value == "competitive"
    assert review.auto_approve_threshold == 90.0