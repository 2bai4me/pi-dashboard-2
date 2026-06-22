"""Task-Metriken + OpenBrain-Capture (Phase 5 + 7 + 8).

User-Direktive 22.06.2026:
  - Auto-Fix-Loop: bei Score < 90 zurueck zu Stage 3, max 3 Iterationen
  - Metriken: Coverage, Reviewer-Score, Code-Quality, Doc-Quality
  - Cost-Guard: Hard-Limits pro Stage + Global Rate-Limit
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pi-dashboard-2.task_metrics")


# === Cost-Limits pro Stage (Hard-Limits) ===

STAGE_COST_LIMITS = {
    "stage0_triage":       0.05,
    "stage1_planning":     0.10,
    "stage2_implementation": 0.50,
    "stage3_multi_test":   0.30,
    "stage4_competitive_review": 0.20,
    "stage5_auto_fix":     0.30,
    "stage6_final":        0.05,
    "stage7_evaluation":   0.05,
}
GLOBAL_COST_LIMIT_PER_HOUR = 5.00  # USD/h
MAX_AUTO_FIX_ITERATIONS = 3


@dataclass
class TaskScore:
    """Konsolidierter Score eines durchlaufenen Tasks."""
    task_id: str
    test_coverage: float = 0.0
    reviewer_score: float = 0.0
    code_quality: float = 0.0
    performance_score: float = 0.0
    doc_quality: float = 0.0
    total_cost_usd: float = 0.0
    iteration_count: int = 0
    auto_approved: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def final_score(self) -> float:
        """Gewichteter Durchschnitt aller Scores (0-100)."""
        weights = {
            "test_coverage": 0.25,
            "reviewer_score": 0.25,
            "code_quality": 0.20,
            "performance_score": 0.15,
            "doc_quality": 0.15,
        }
        score = (
            self.test_coverage * weights["test_coverage"]
            + self.reviewer_score * weights["reviewer_score"]
            + self.code_quality * weights["code_quality"]
            + self.performance_score * weights["performance_score"]
            + self.doc_quality * weights["doc_quality"]
        )
        return round(score, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["final_score"] = self.final_score
        return d


# === Auto-Fix-Loop Logic ===

def should_auto_fix(score: float, iteration_count: int) -> bool:
    """Entscheidet ob Auto-Fix-Loop gestartet werden soll."""
    return score < 90.0 and iteration_count < MAX_AUTO_FIX_ITERATIONS


def get_next_iteration_action(score: float, iteration_count: int) -> Dict[str, Any]:
    """Liefert die naechste Aktion basierend auf Score + Iterations-Counter."""
    if should_auto_fix(score, iteration_count):
        return {
            "action": "auto_fix",
            "reason": f"Score {score:.1f} < 90, Iteration {iteration_count + 1}/{MAX_AUTO_FIX_ITERATIONS}",
            "next_step": "stage5_auto_fix",
            "target_stage_after_fix": "stage3_multi_test",
        }
    if score < 90.0 and iteration_count >= MAX_AUTO_FIX_ITERATIONS:
        return {
            "action": "escalate",
            "reason": f"Max iterations ({MAX_AUTO_FIX_ITERATIONS}) erreicht, Score {score:.1f} < 90",
            "next_step": "human_review",
        }
    return {
        "action": "approve",
        "reason": f"Score {score:.1f} >= 90, Auto-Approve",
        "next_step": "stage6_final",
    }


# === Cost-Guard ===

class CostGuard:
    """Ueberwacht kumulierte Kosten, Hard-Limit pro Stunde."""

    def __init__(self, hourly_limit_usd: float = GLOBAL_COST_LIMIT_PER_HOUR):
        self.hourly_limit_usd = hourly_limit_usd
        self._hour_start_ts = int(time.time() // 3600) * 3600
        self._current_hour_spend = 0.0

    def can_spend(self, amount_usd: float) -> bool:
        """Prueft ob `amount_usd` im aktuellen Stundenbudget verfuegbar ist."""
        self._maybe_rollover_hour()
        return (self._current_hour_spend + amount_usd) <= self.hourly_limit_usd

    def record_spend(self, amount_usd: float) -> None:
        """Zeichnet Ausgabe auf und prueft Hard-Limit."""
        self._maybe_rollover_hour()
        self._current_hour_spend += amount_usd
        if self._current_hour_spend > self.hourly_limit_usd:
            logger.error(
                f"Cost-Guard: Hard-Limit ueberschritten! "
                f"${self._current_hour_spend:.2f} > ${self.hourly_limit_usd:.2f}"
            )

    def _maybe_rollover_hour(self) -> None:
        """Setzt Counter zurueck wenn neue Stunde begonnen hat."""
        now_hour = int(time.time() // 3600) * 3600
        if now_hour > self._hour_start_ts:
            self._hour_start_ts = now_hour
            self._current_hour_spend = 0.0

    def get_status(self) -> Dict[str, Any]:
        """Liefert aktuellen Status fuer Monitoring."""
        return {
            "hourly_limit_usd": self.hourly_limit_usd,
            "current_spend_usd": round(self._current_hour_spend, 4),
            "remaining_usd": round(self.hourly_limit_usd - self._current_hour_spend, 4),
            "hour_started_at": datetime.fromtimestamp(self._hour_start_ts, timezone.utc).isoformat(),
            "limit_warning_at_80pct": self._current_hour_spend >= 0.8 * self.hourly_limit_usd,
            "limit_exceeded": self._current_hour_spend > self.hourly_limit_usd,
        }


# === Task Score DB-Operationen ===

def persist_task_score(score: TaskScore) -> None:
    """Speichert Task-Score in der DB.

    Nutzt tasks.meta JSON-Feld fuer die Persistierung (kein Schema-Change noetig).
    """
    conn = sqlite3.connect("database/pi_dashboard.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET meta = json_set(COALESCE(meta, '{}'), '$.task_score', ?) WHERE id = ?",
        (json.dumps(score.to_dict()), score.task_id),
    )
    conn.commit()
    conn.close()


def get_task_score(task_id: str) -> Optional[TaskScore]:
    """Laedt Task-Score aus tasks.meta."""
    conn = sqlite3.connect("database/pi_dashboard.db")
    cur = conn.cursor()
    cur.execute("SELECT meta FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        meta = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except (json.JSONDecodeError, TypeError):
        return None
    score_data = meta.get("task_score")
    if not score_data:
        return None
    return TaskScore(**{k: v for k, v in score_data.items() if k != "final_score"})


# === OpenBrain-Capture (Self-Evaluation Stage 7) ===

def capture_to_openbrain(task_id: str, score: TaskScore, sop_id: str) -> Dict[str, Any]:
    """Speichert Task-Evaluation im OpenBrain (via HTTP-Call).

    User-Direktive 22.06.2026: Self-Evaluation als Capture fuer Learning.
    Bei Fehler: nur Log, kein Hard-Fail (Self-Eval darf nicht alles blockieren).
    """
    import os
    import urllib.request
    openbrain_url = os.environ.get("OPENBRAIN_DEV_URL", "http://localhost:9303")
    openbrain_key = os.environ.get("OPENBRAIN_DEV_KEY", "ob-dev-key-2026")

    content = (
        f"[PI-Dashboard 2.0 Swarm-Self-Eval] Task {task_id[:8]} abgeschlossen\n"
        f"────────────────────────────────────────\n"
        f"Final Score: {score.final_score:.1f}/100\n"
        f"Auto-Approved: {score.auto_approved}\n"
        f"Iterations: {score.iteration_count}\n"
        f"Cost: ${score.total_cost_usd:.2f}\n"
        f"Reviewer-Score: {score.reviewer_score:.1f}\n"
        f"Test-Coverage: {score.test_coverage:.1f}%\n"
        f"Code-Quality: {score.code_quality:.1f}\n"
        f"Performance: {score.performance_score:.1f}\n"
        f"Doku: {score.doc_quality:.1f}\n"
        f"\nQuelle: SOP 7c86692be939 (Staged Hybrid Swarm)\n"
        f"Tags: [pi-dashboard-2, swarm, self-eval, automation]"
    )

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": f"self-eval-{task_id[:8]}",
        "method": "tools/call",
        "params": {
            "name": "capture_thought",
            "arguments": {
                "content": content,
                "type": "observation",
                "tags": ["pi-dashboard-2", "swarm", "self-eval", "automation"],
            },
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            openbrain_url, data=payload,
            headers={"Content-Type": "application/json", "x-brain-key": openbrain_key},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"ok": resp.status == 200, "status_code": resp.status}
    except Exception as e:
        logger.warning(f"OpenBrain-Capture fehlgeschlagen: {e}")
        return {"ok": False, "error": str(e)}