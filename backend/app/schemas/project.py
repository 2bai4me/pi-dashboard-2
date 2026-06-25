"""Project Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "active"
    mode: str = "preparation"  # preparation | execution | paused | completed
    category: str = "new_request"  # new_request | ticket | change (ITIL)


class ProjectCreate(ProjectBase):
    """POST /api/kanban/projects — Neues Projekt anlegen."""
    pass


class ProjectUpdate(BaseModel):
    """PATCH /api/kanban/projects/{id} — Update Felder."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    mode: Optional[str] = None
    category: Optional[str] = None
    completion_report: Optional[str] = None
    default_sop_id: Optional[str] = None  # User-Direktive 15.06.2026: Standard-SOP-Auswahl im UI


class ProjectModeUpdate(BaseModel):
    """PUT /api/kanban/projects/{id}/mode — Modus wechseln (User-Direktive 15.06.2026)."""
    mode: str = Field(..., pattern="^(preparation|execution|paused|completed)$")
    note: Optional[str] = None


class ProjectCategoryUpdate(BaseModel):
    """PUT /api/kanban/projects/{id}/category — ITIL-Klassifizierung."""
    category: str = Field(..., pattern="^(new_request|ticket|change)$")


class CompletionReport(BaseModel):
    """Generierter Abschlussbericht bei mode=completed."""
    project_id: str
    project_name: str
    completed_at: datetime
    duration_days: int
    task_stats: Dict[str, int]  # status -> count
    total_tokens: Dict[str, int]  # in, out
    total_cost_usd: float
    cost_by_provider: Dict[str, float]
    cost_by_role: Dict[str, float]
    cost_by_model: Dict[str, float]
    top_5_expensive_tasks: List[Dict[str, Any]]
    summary_text: str


class ProjectRead(ProjectBase):
    """Response: Vollständiges Projekt inkl. Stats."""
    id: str
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    completion_report: Optional[str] = None
    default_sop_id: Optional[str] = None  # User-Direktive 15.06.2026
    project_number: Optional[str] = None  # User-Direktive 23.06.2026, Task 260326669e82
    task_count: int = 0
    tasks_done: int = 0
    tasks_cancelled: int = 0  # FIX 23.06.2026 (Task dad90780eb76)
    tasks_in_progress: int = 0
    # === FIX 23.06.2026 (Task dad90780eb76): tasks_open field ===
    # Anzahl der offenen Tasks (nicht done, nicht cancelled).
    # Frontend-Kachel zeigt prominent die Anzahl offener Tasks.
    tasks_open: int = 0
    total_cost_usd: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class ProjectList(BaseModel):
    """Liste von Projects (kompakte Form für Kachel-View)."""
    items: List[ProjectRead]
    total: int
