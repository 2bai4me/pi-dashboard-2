"""Pi Dashboard 2.0 — Pydantic v2 Schemas (Request/Response)."""
from .project import (
    ProjectRead, ProjectCreate, ProjectUpdate, ProjectList,
    ProjectModeUpdate, ProjectCategoryUpdate, CompletionReport,
)
from .task import (
    TaskRead, TaskCreate, TaskUpdate, TaskList,
    TaskStatusUpdate, TaskPriorityUpdate, TaskDispatchUpdate,
    TaskTokenReport, TaskWithStats, TaskStats, TaskHistoryEntry,
    SubTaskCreate, SubTaskCreateList,
)
from .transition import (
    TaskTransitionRead, TaskTransitionList, ProjectTransitionTimeline,
)
from .role import RoleRead, RoleCreate, RoleUpdate, RoleList
from .pricing import (
    ModelPricingRead, PricingUpdateRequest, PricingRefreshResult,
    ModelInfo, ProviderInfo,
)
from .agent_question import (
    AgentQuestionCreate, AgentQuestionAnswer,
    AgentQuestionRead, AgentQuestionDetail, AgentQuestionList,
    AgentQuestionAttachmentRead,
)

__all__ = [
    # Project
    "ProjectRead", "ProjectCreate", "ProjectUpdate", "ProjectList",
    "ProjectModeUpdate", "ProjectCategoryUpdate", "CompletionReport",
    # Task
    "TaskRead", "TaskCreate", "TaskUpdate", "TaskList",
    "TaskStatusUpdate", "TaskPriorityUpdate", "TaskDispatchUpdate",
    "TaskTokenReport", "TaskWithStats", "TaskStats", "TaskHistoryEntry",
    "SubTaskCreate", "SubTaskCreateList",
    # Transition
    "TaskTransitionRead", "TaskTransitionList", "ProjectTransitionTimeline",
    # Role
    "RoleRead", "RoleCreate", "RoleUpdate", "RoleList",
    # Pricing
    "ModelPricingRead", "PricingUpdateRequest", "PricingRefreshResult",
    "ModelInfo", "ProviderInfo",
    # AgentQuestion (User <-> Agent Interaktion)
    "AgentQuestionCreate", "AgentQuestionAnswer",
    "AgentQuestionRead", "AgentQuestionDetail", "AgentQuestionList",
    "AgentQuestionAttachmentRead",
]
