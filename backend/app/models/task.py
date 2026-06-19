"""Task-Model + Subtask-Relation."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Any
from sqlalchemy import String, Text, DateTime, Integer, Boolean, ForeignKey, Index, JSON, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base

if TYPE_CHECKING:
    from .project import Project
    from .history import TaskHistory
    from .token_usage import TokenUsage


class JSONType(TypeDecorator):
    """JSON-Typ, der fuer SQLite zu Text serialisiert und fuer PostgreSQL JSONB nutzt.

    Python-Listen/Dicts werden automatisch zu JSON-String serialisiert beim INSERT
    und wieder deserialisiert beim SELECT.
    """
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        # SQLite: serialize zu JSON-String
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


class Task(Base):
    """Ein Task im Kanban-Board.

    Status (v2.1 — User-Direktive 15.06.2026):
      triage      = Inhalt unklar, braucht Klarung
      todo        = CIO-freigegeben, alles klar, kann losgelegt werden
      in_progress = aktiv in Bearbeitung
      review      = zur Review (Sub-Agent hat fertig gemeldet)
      rueckfrage  = CIO-Frage an CEO/CEO-digital, Input benotigt
      warten      = wartet auf Ergebnis eines anderen Tasks (z.B. Sub-Task-Gate)
      done        = fertig

    Category (ITIL): new_request | ticket | change
    Priority: 0-100 (NOTFALL ab 90)
    """
    __tablename__ = "tasks"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Foreign Keys ===
    project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE")
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="CASCADE")
    )

    # === Felder ===
    # Standard-Defaults gemaess SOP 'task-creation-default' (User-Direktive 15.06.2026):
    #   status   = 'triage'  (neue Tasks starten IMMER in Triage)
    #   priority = 1         (CIO bewertet im Triage-Prozess, hebt Prio an)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="triage", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="new_request", nullable=False)
    assigned_role: Mapped[Optional[str]] = mapped_column(String(64))
    assigned_subagent: Mapped[Optional[str]] = mapped_column(String(64))

    # === Counter / Sortierung ===
    iteration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Flags ===
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # === JSON-Felder (Pricing-Snapshot, Tags, Criteria, Meta) ===
    pricing_snapshot: Mapped[Optional[dict]] = mapped_column(JSONType)
    tags: Mapped[Optional[list]] = mapped_column(JSONType, default=list)
    success_criteria: Mapped[Optional[list]] = mapped_column(JSONType, default=list)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === CIO-Triage-Felder (User-Direktive 16.06.2026, Schritt 0) ===
    # task_type: Konkreter Typ, vom CIO in Schritt 0 klassifiziert
    #            (z.B. "new_request" | "change" | "ticket" | "bugfix")
    task_type: Mapped[Optional[str]] = mapped_column(String(32))

    # implementation_plan: Strukturierte App-Aenderungs-Beschreibung (CIO ergaenzt)
    #            (z.B. {"files": [...], "routes": [...], "api_changes": [...]})
    implementation_plan: Mapped[Optional[dict]] = mapped_column(JSONType)

    # standards_check: Ergebnis der OpenBrain-Pruefung (CIO bewertet)
    #            (z.B. {"checked_at": "...", "matches": [...], "missing": [...], "notes": "..."})
    standards_check: Mapped[Optional[dict]] = mapped_column(JSONType)

    # subagent_readiness: Bewertung der Subagent-Readiness (CIO prueft)
    #            (z.B. {"model": "minimax-m3", "branch": "task/123", ...})
    subagent_readiness: Mapped[Optional[dict]] = mapped_column(JSONType)

    # === Relations ===
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="tasks")
    parent: Mapped[Optional["Task"]] = relationship(
        "Task", remote_side=[id], backref="subtasks"
    )
    history_entries: Mapped[List["TaskHistory"]] = relationship(
        "TaskHistory", back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )
    token_usages: Mapped[List["TokenUsage"]] = relationship(
        "TokenUsage", back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_tasks_project_id", "project_id"),
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_priority_desc", "priority"),
        Index("idx_tasks_assigned_role", "assigned_role"),
        Index("idx_tasks_emergency", "emergency"),
        Index("idx_tasks_project_status", "project_id", "status"),
        Index("idx_tasks_created_at_desc", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Task {self.id[:8]} [{self.status}] prio={self.priority} '{self.title[:30]}'>"
