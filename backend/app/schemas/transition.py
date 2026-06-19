"""Pydantic-Schemas fuer TaskTransition (zentrale Performance-Tabelle)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TaskTransitionRead(BaseModel):
    """Eine Status-Transition (Performance-Record)."""
    id: int
    task_id: str
    project_id: Optional[str] = None
    from_status: str
    to_status: str
    # === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    # Display-Namen fuer die UI (z.B. "todo" -> "GO", "in_progress" -> "In Progress").
    # Das DB-Feld bleibt unveraendert (status-Label), aber die API liefert
    # zusaetzlich die Anzeige-Namen, damit das Performance-Frontend die
    # user-freundlichen Texte rendern kann.
    from_status_display: Optional[str] = None
    to_status_display: Optional[str] = None
    transition_at: datetime
    processing_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    delay_s: float
    duration_ms: Optional[int] = None
    agent: Optional[str] = None
    reason: Optional[str] = None
    details: Optional[dict] = Field(default_factory=dict)
    session_id: Optional[str] = None  # User-Direktive 18.06.2026: Session-Tracking

    class Config:
        from_attributes = True


class TaskTransitionList(BaseModel):
    """Liste von Transitions mit Statistik-Aggregation."""
    items: List[TaskTransitionRead]
    total: int
    project_id: Optional[str] = None
    stats: Optional[dict] = None


class ProjectTransitionTimeline(BaseModel):
    """Timeline aller Transitions fuer ein Projekt."""
    project_id: str
    items: List[TaskTransitionRead]
    total: int
    summary: dict
