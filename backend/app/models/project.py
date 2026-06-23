"""Project-Model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base

if TYPE_CHECKING:
    from .task import Task


class Project(Base):
    """Ein Projekt im Kanban-System.

    Modi (User-Direktive 15.06.2026):
    - preparation: Tasks werden angelegt, KANBAN laeuft noch nicht
    - execution: CIO + Operator arbeiten alle Tasks ab (Multi/Swarm Agent)
    - paused: Umsetzung gestoppt
    - completed: Wie paused, aber mit Abschlussbericht
    """
    __tablename__ = "projects"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Felder ===
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="preparation", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="new_request", nullable=False)

    # === Projektnummer (User-Direktive 23.06.2026, Task 260326669e82) ===
    # Format: PROJ-YYYY-NNN (z.B. PROJ-2026-001), eindeutig pro Projekt
    project_number: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Completion-Report (JSON, nur bei mode=completed) ===
    completion_report: Mapped[Optional[str]] = mapped_column(Text)

    # === Default-SOP (User-Direktive 15.06.2026) ===
    # Welche SOP soll fuer den Prozessdurchlauf genutzt werden?
    # Wird vom User im UI ausgewaehlt (Dropdown neben Mode-Switcher).
    # Die Rule-Engine (SOP-Funktion) liest dieses Feld spaeter aus.
    default_sop_id: Mapped[Optional[str]] = mapped_column(String(32))

    # === Relations ===
    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_projects_status", "status"),
        Index("idx_projects_mode", "mode"),
        Index("idx_projects_category", "category"),
        Index("idx_projects_created_at", "created_at"),
        Index("idx_projects_default_sop", "default_sop_id"),
    )

    def __repr__(self) -> str:
        return f"<Project {self.id[:8]} '{self.name}' mode={self.mode}>"
