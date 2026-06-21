"""SOP-Action-Schemas und Whitelist.

Dieses Modul zentralisiert die erlaubten Actions fuer die SOP-Engine und
liefert Pydantic-Schemas zur Validierung von action_params.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# === Whitelist aller erlaubten SOP-Actions ===
# Hinweis: Die Whitelist muss alle Actions enthalten, die _execute_action
# aktuell beherrscht, plus zukuenftige/geplante Actions, damit bestehende
# SOPs nicht ploetzlich abgelehnt werden.
ALLOWED_ACTIONS = frozenset(
    {
        # generische / zukuenftige Actions (lt. Aufgabenstellung)
        "noop",
        "set_status",
        "ask_user",
        "llm_call",
        "spawn_sop",
        "review_task",
        "assign_worker",
        "implement",
        "test",
        "cio_final_review",
        "tester_code_review",
        # bestehende Workflow-Actions, die _execute_action bereits behandelt
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
        "collect_issue",
    }
)


# === Pydantic-Schemas fuer action_params ===

class SetStatusActionParams(BaseModel):
    """Parameter fuer Statuswechsel-Actions (set_status / move_status)."""

    status: str = Field(..., min_length=1, description="Ziel-Status des Tasks")


class AskUserActionParams(BaseModel):
    """Parameter fuer die ask_user-Action (blockierende User-Rueckfrage)."""

    question: str = Field(..., min_length=1, description="Frage an den User")
    context_key: Optional[str] = Field(
        None, description="Schluessel unter dem die Antwort im Instance-Context gespeichert wird"
    )
    options: Optional[List[str]] = Field(
        None, description="Optionale Auswahl-Optionen"
    )


class LLMCallActionParams(BaseModel):
    """Parameter fuer einen LLM-Aufruf innerhalb eines SOP-Steps."""

    prompt: str = Field(..., min_length=1, description="Prompt fuer das LLM")
    model: Optional[str] = Field(None, description="Zu verwendendes Modell")
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Sampling-Temperatur"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, description="Maximale Token-Anzahl"
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


# Mapping: action -> Pydantic-Schema fuer action_params
ACTION_PARAM_SCHEMAS: Dict[str, type[BaseModel]] = {
    "set_status": SetStatusActionParams,
    "move_status": SetStatusActionParams,
    "ask_user": AskUserActionParams,
    "llm_call": LLMCallActionParams,
    "spawn_sop": SpawnSopActionParams,
}
