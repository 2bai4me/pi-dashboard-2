"""SOP-Action-Schemas und Whitelist.

Dieses Modul zentralisiert die erlaubten Actions fuer die SOP-Engine und
liefert Pydantic-Schemas zur Validierung von action_params.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# === Whitelist aller erlaubten SOP-Actions ===
# Hinweis: Diese Whitelist ist die EINZIGE Quelle der Wahrheit fuer die Engine.
# Sie enthaelt nur Actions, die _execute_action / _execute_triage_action
# tatsaechlich beherrschen. Geplante/nicht implementierte Actions duerfen hier
# NICHT stehen, damit sie nicht zur Laufzeit fehlschlagen.
ALLOWED_ACTIONS = frozenset(
    {
        "noop",
        "llm_call",
        "spawn_sop",
        "review_task",
        "assign_worker",
        "cio_final_review",
        "tester_code_review",
        # Workflow-Actions
        "move_status",
        "approve_triage",
        "start_work",
        "submit_review",
        "tester_approve",
        "tester_reject",
        "cio_final_approve",
        "cio_final_reject",
        # CIO-Triage-Check-Actions
        "check_title",
        "check_description",
        "check_success_criteria",
        "check_architecture",
        "check_consistency",
        "decide_triage",
        # Multi-Agent-Swarm (User-Direktive 22.06.2026)
        "spawn_swarm",
        # Self-Evaluation (User-Direktive 23.06.2026)
        "evaluate_outcome",
        # Task-Decomposition (User-Direktive 23.06.2026, Task 4bf7146b0780)
        "decompose_task",
    }
)


# === Pydantic-Schemas fuer action_params ===

class MoveStatusActionParams(BaseModel):
    """Parameter fuer Statuswechsel-Actions (move_status / aehnlich)."""

    status: str = Field(..., min_length=1, description="Ziel-Status des Tasks")


class LLMCallActionParams(BaseModel):
    """Parameter fuer einen LLM-Aufruf innerhalb eines SOP-Steps."""

    user_prompt: str = Field(..., min_length=1, description="User-Prompt fuer das LLM")
    system_prompt: Optional[str] = Field(
        None, description="Optionaler System-Prompt"
    )
    model: Optional[str] = Field(None, description="Zu verwendendes Modell")
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Sampling-Temperatur"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, le=16000, description="Maximale Token-Anzahl"
    )
    timeout_sec: Optional[float] = Field(
        None, ge=0.001, le=300.0, description="LLM-Timeout in Sekunden"
    )
    response_format: Optional[Dict[str, Any]] = Field(
        None, description="OpenAI-compatible response_format"
    )
    instructions_md: Optional[str] = Field(
        None, description="Markdown-Anweisungen fuer den Agent"
    )


class SpawnSopActionParams(BaseModel):
    """Parameter fuer das Starten einer Sub-SOP."""

    sop_id: str = Field(..., min_length=1, description="ID der zu startenden Sub-SOP")
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Kontext-Variablen fuer die Sub-SOP"
    )


class SpawnSwarmActionParams(BaseModel):
    """Parameter fuer das Starten eines Multi-Agent-Swarms.

    User-Direktive 22.06.2026: Staged Hybrid Swarm fuer hoechste Qualitaet.
    Der Swarm-Spawner orchestriert mehrere SubAgents parallel oder kompetitiv.
    """

    swarm_type: str = Field(
        "parallel",
        description="Swarm-Typ: single | parallel | competitive",
    )
    workers: List[Dict[str, Any]] = Field(
        ..., min_length=1, description="Liste der Worker-Konfigurationen"
    )
    merge_strategy: str = Field(
        "reviewer_picks_best",
        description="Merge-Strategie: reviewer_picks_best | merge_all | consensus_score | first_success",
    )
    consensus_threshold: float = Field(
        75.0, ge=0.0, le=100.0, description="Score-Schwelle fuer Konsens"
    )
    auto_approve_threshold: float = Field(
        90.0, ge=0.0, le=100.0, description="Score-Schwelle fuer Auto-Approve"
    )
    max_cost_usd: float = Field(
        0.50, ge=0.0, description="Hard-Limit fuer Swarm-Kosten"
    )
    timeout_sec: int = Field(
        600, ge=1, description="Timeout fuer den gesamten Swarm"
    )
    stage_key: Optional[str] = Field(
        None,
        description="Stage-Key fuer Default-Config (z.B. 'stage2_implementation')",
    )


# Mapping: action -> Pydantic-Schema fuer action_params
ACTION_PARAM_SCHEMAS: Dict[str, type[BaseModel]] = {
    "move_status": MoveStatusActionParams,
    "approve_triage": MoveStatusActionParams,
    "start_work": MoveStatusActionParams,
    "submit_review": MoveStatusActionParams,
    "tester_approve": MoveStatusActionParams,
    "tester_reject": MoveStatusActionParams,
    "cio_final_approve": MoveStatusActionParams,
    "cio_final_reject": MoveStatusActionParams,
    "llm_call": LLMCallActionParams,
    "spawn_sop": SpawnSopActionParams,
    "spawn_swarm": SpawnSwarmActionParams,
}
