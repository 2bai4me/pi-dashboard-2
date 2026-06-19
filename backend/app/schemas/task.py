"""Task Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    """Pydantic-Schema-Basis fuer Task.

    Standard-Defaults (User-Direktive 15.06.2026, Skill kanban-operator + SOP
    'task-creation-default'):
      - status   = 'triage'  (neue Tasks starten IMMER in Triage)
      - priority = 1         (CIO bewertet im Triage-Prozess, hebt Prio an)
      - category = 'new_request'
    """
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    status: str = "triage"
    priority: int = Field(1, ge=0, le=100)
    category: str = "new_request"  # ITIL: new_request | ticket | change
    assigned_role: Optional[str] = None
    success_criteria: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class TaskCreate(TaskBase):
    """POST /api/kanban/tasks — Neuer Task."""
    project_id: Optional[str] = None
    parent_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """PATCH /api/kanban/tasks/{id} — Update Felder."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=100)
    category: Optional[str] = None
    assigned_role: Optional[str] = None
    assigned_subagent: Optional[str] = None
    success_criteria: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class TaskStatusUpdate(BaseModel):
    """PUT /api/kanban/tasks/{id}/status — Status setzen (loest auto_claim aus)."""
    status: str
    note: Optional[str] = None


class TaskPriorityUpdate(BaseModel):
    """PUT /api/kanban/tasks/{id}/priority — Prio setzen (loest emergency_watchdog aus ab 90)."""
    priority: int = Field(..., ge=0, le=100)


class TaskDispatchUpdate(BaseModel):
    """PATCH /api/kanban/tasks/{id}/dispatch — Sub-Agent meldet Status zurueck."""
    role: Optional[str] = None
    status: Optional[str] = None  # dispatching | dispatched | dry-run | done
    model: Optional[str] = None
    agent_pid: Optional[int] = None
    ts: Optional[str] = None
    reason: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0


class TaskTokenReport(BaseModel):
    """POST /api/kanban/tasks/{id}/usage — Sub-Agent meldet kumulierte Token-Counts."""
    model: Optional[str] = None
    role: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    note: Optional[str] = None


class TaskHistoryEntry(BaseModel):
    """Ein History-Eintrag in der Task-Audit-Log."""
    id: int
    ts: datetime
    event: str
    agent: Optional[str] = None
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)
    # === User-Direktive 18.06.2026: Display-Mapping (z.B. 'todo' -> 'GO') ===
    # details_mapped: Dict[str, Any] wird vom Router befuellt (translate_history_details)

    model_config = ConfigDict(from_attributes=True)


class TaskRead(TaskBase):
    """Response: Vollständiger Task."""
    id: str
    project_id: Optional[str] = None
    parent_id: Optional[str] = None
    assigned_subagent: Optional[str] = None
    iteration_count: int = 0
    order: int = 0
    created_at: datetime
    updated_at: datetime
    claimed_at: Optional[datetime] = None
    emergency: bool = False
    pricing_snapshot: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    # === CIO-Triage-Felder (User-Direktive 16.06.2026, Schritt 0) ===
    task_type: Optional[str] = None
    implementation_plan: Optional[Dict[str, Any]] = None
    standards_check: Optional[Dict[str, Any]] = None
    subagent_readiness: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)


class TaskList(BaseModel):
    """Liste von Tasks (paginiert)."""
    items: List[TaskRead]
    total: int
    limit: int = 100
    offset: int = 0


class TaskStats(BaseModel):
    """GET /api/kanban/tasks/{id}/stats — Aggregierte Stats."""
    task_id: str
    model: str
    model_usage: Dict[str, int]
    tokens: Dict[str, int]  # in, out, total
    cost_usd: float
    duration_s: int
    history_count: int
    pricing_snapshot: Optional[Dict[str, Any]] = None


class SubTaskCreate(BaseModel):
    """POST /api/kanban/tasks/{id}/subtasks — Sub-Tasks anlegen."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    priority: int = Field(50, ge=0, le=100)
    category: str = "new_request"
    assigned_role: Optional[str] = None
    success_criteria: List[str] = Field(default_factory=list)


class SubTaskCreateList(BaseModel):
    """Wrapper fuer POST subtasks Body (Pydantic-ForwardRef Workaround)."""
    subtasks: List[SubTaskCreate]


class TaskWithStats(TaskRead):
    """Task + Stats (für Sidebar-Anzeige)."""
    stats: TaskStats
    # === User-Direktive 18.06.2026: Display-Mapping ===
    status_display: Optional[str] = None  # z.B. 'GO' statt 'todo'
