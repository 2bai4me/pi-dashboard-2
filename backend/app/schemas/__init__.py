"""Pi Dashboard 2.0 — Pydantic v2 Schemas (Request/Response)."""
from .project import (
    ProjectRead, ProjectCreate, ProjectUpdate, ProjectList,
    ProjectModeUpdate, ProjectCategoryUpdate, CompletionReport,
)
from .task import (
    TaskRead, TaskCreate, TaskUpdate, TaskList,
    TaskStatusUpdate, TaskPriorityUpdate, TaskDispatchUpdate,
    TaskTokenReport, TaskWithStats, TaskStats, TaskHistoryEntry,
)
from .role import RoleRead, RoleCreate, RoleUpdate, RoleList
from .pricing import (
    ModelPricingRead, PricingUpdateRequest, PricingRefreshResult,
    ModelInfo, ProviderInfo,
)

__all__ = [
    # Project
    "ProjectRead", "ProjectCreate", "ProjectUpdate", "ProjectList",
    "ProjectModeUpdate", "ProjectCategoryUpdate", "CompletionReport",
    # Task
    "TaskRead", "TaskCreate", "TaskUpdate", "TaskList",
    "TaskStatusUpdate", "TaskPriorityUpdate", "TaskDispatchUpdate",
    "TaskTokenReport", "TaskWithStats", "TaskStats", "TaskHistoryEntry",
    # Role
    "RoleRead", "RoleCreate", "RoleUpdate", "RoleList",
    # Pricing
    "ModelPricingRead", "PricingUpdateRequest", "PricingRefreshResult",
    "ModelInfo", "ProviderInfo",
]
