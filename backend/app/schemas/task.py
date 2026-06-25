"""Task Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# === ImplementationPlan Schemas (FIX 23.06.2026, Task 9f2f473bf1cc) ===
# Strukturierter Plan, der von pi-architect (SOP Step 1) und CIO (SOP Step 0) befuellt wird.
# Wird automatisch in task.implementation_plan geschrieben und im Frontend angezeigt.

class FileChangeType(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class AffectedFile(BaseModel):
    path: str = Field(..., min_length=1, max_length=500, description="Relativer Pfad zur Datei, z.B. 'src/api/foo.py'")
    change_type: FileChangeType
    description: str = Field(..., min_length=1, max_length=1000, description="Was wird an dieser Datei geaendert")


class ApiChange(BaseModel):
    method: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE)$", description="HTTP-Methode")
    path: str = Field(..., min_length=1, max_length=500, description="API-Pfad, z.B. '/api/kanban/tasks'")
    request_schema: Optional[str] = Field(None, description="JSON-Schema oder TypeScript-Interface des Request-Body")
    response_schema: Optional[str] = Field(None, description="JSON-Schema oder TypeScript-Interface der Response")
    breaking: bool = False


class DbChangeType(str, Enum):
    CREATE_TABLE = "create_table"
    ALTER_TABLE = "alter_table"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"


class DbChange(BaseModel):
    type: DbChangeType
    target: str = Field(..., min_length=1, max_length=200, description="Betroffene Tabelle oder Index-Name")
    details: str = Field(..., min_length=1, max_length=2000, description="Details zur Aenderung (SQL-Skizze oder Erklaerung)")


class SubTask(BaseModel):
    id: str = Field(..., pattern=r"^st[1-9][0-9]*$", description="z.B. 'st1', 'st2'")
    title: str = Field(..., min_length=1, max_length=200)
    assigned_role: str = Field(..., description="z.B. 'pi-coder', 'pi-tester', 'pi-reviewer'")
    depends_on: List[str] = Field(default_factory=list, description="IDs anderer Sub-Tasks (z.B. ['st1', 'st2'])")
    estimate_min: int = Field(..., ge=1, le=480, description="Geschaetzte Minuten (max 8h pro Sub-Task)")


class AcceptanceCriterion(BaseModel):
    id: str = Field(..., pattern=r"^ac[1-9][0-9]*$", description="z.B. 'ac1', 'ac2'")
    description: str = Field(..., min_length=1, max_length=500)
    test_method: str = Field(..., description="z.B. 'unit', 'integration', 'e2e', 'manual'")
    expected: str = Field(..., min_length=1, max_length=500, description="Was wird erwartet (messbar)")


class Risk(BaseModel):
    id: str = Field(..., pattern=r"^r[1-9][0-9]*$", description="z.B. 'r1', 'r2'")
    description: str = Field(..., min_length=1, max_length=500)
    likelihood: int = Field(..., ge=1, le=5, description="1=sehr unwahrscheinlich, 5=fast sicher")
    impact: int = Field(..., ge=1, le=5, description="1=vernachlaessigbar, 5=katastrophal")
    mitigation: str = Field(..., min_length=1, max_length=1000, description="Wie wird das Risiko mitigiert")


class Dependency(BaseModel):
    type: str = Field(..., pattern=r"^(internal|external|service)$")
    ref: str = Field(..., min_length=1, max_length=200, description="z.B. 'task:abc123', 'service:ME4-PI', 'lib:react'")
    status: str = Field(..., pattern=r"^(ready|blocked|partial)$")


class ImplementationPlan(BaseModel):
    """Strukturierter Implementierungs-Plan fuer einen Task.

    Wird vom pi-architect (SOP Step 1) und CIO (SOP Step 0) befuellt.
    Bei Validierungs-Fehlern wird HTTP 400 zurueckgegeben mit Detail-Liste.

    Beispiel-Mindestfuellung:
    {
        "summary": "Login mit OAuth2 einbauen",
        "context": "User-Direktive 15.06.2026: Auth provider fehlt",
        "affected_files": [],
        "sub_tasks": [],
        "acceptance_criteria": []
    }
    """
    summary: str = Field(..., min_length=1, max_length=500, description="1 Satz, was wird gemacht")
    context: Optional[str] = Field(None, max_length=2000, description="Warum, Bezug zu Anforderungen")
    affected_files: List[AffectedFile] = Field(default_factory=list)
    api_changes: List[ApiChange] = Field(default_factory=list)
    db_changes: List[DbChange] = Field(default_factory=list)
    sub_tasks: List[SubTask] = Field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    risks: List[Risk] = Field(default_factory=list)
    dependencies: List[Dependency] = Field(default_factory=list)
    test_strategy: Optional[str] = Field(None, max_length=2000, description="1-2 Saetze, wie wird getestet")
    rollout_plan: Optional[str] = Field(None, max_length=2000, description="1-2 Saetze, Reihenfolge + Feature-Flag")
    notes: Optional[str] = Field(None, max_length=5000, description="Freitext-Notizen")
    # === Metadata ===
    created_by: Optional[str] = Field(None, description="'CIO' | 'pi-architect' | 'manual'")
    created_at: Optional[datetime] = None
    version: int = Field(default=1, ge=1, description="Bei Updates inkrementieren")

    @field_validator("sub_tasks")
    @classmethod
    def check_unique_subtask_ids(cls, v: List[SubTask]) -> List[SubTask]:
        ids = [st.id for st in v]
        if len(ids) != len(set(ids)):
            raise ValueError(f"sub_tasks IDs nicht eindeutig: {ids}")
        return v

    @field_validator("acceptance_criteria")
    @classmethod
    def check_unique_criteria_ids(cls, v: List[AcceptanceCriterion]) -> List[AcceptanceCriterion]:
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError(f"acceptance_criteria IDs nicht eindeutig: {ids}")
        return v

    @field_validator("dependencies")
    @classmethod
    def check_deps_exist_in_subtasks(cls, v: List[Dependency], info) -> List[Dependency]:
        sub_tasks = info.data.get("sub_tasks", [])
        sub_task_ids = {st.id for st in sub_tasks}
        for dep in v:
            for d in dep.ref.split(","):
                d = d.strip()
                if d.startswith("task:") and d not in sub_task_ids:
                    # task:xyz referenziert externe Tasks, OK
                    continue
                if d in sub_task_ids:
                    continue
        return v


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
    component_id: Optional[int] = None  # User-Direktive 24.06.2026: Component-Routing durch CIO


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
    # === FIX 23.06.2026 (Task 0973563537c4): project_id darf geupdated werden ===
    # Wichtig: Erlaubt das Korrigieren von Orphan-Tasks (project_id=null).
    # Self-Tracking-Tasks (z.B. ME4-PI-Integration) koennen mit null bleiben.
    project_id: Optional[str] = None


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
