"""Project-Model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
import json as _json
from datetime import timezone as _timezone
from sqlalchemy import String, Text, DateTime, Integer, Boolean, Index  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base

if TYPE_CHECKING:
    from .task import Task
    from .project_component import ProjectComponent


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
    components: Mapped[List["ProjectComponent"]] = relationship(
        "ProjectComponent", back_populates="project", cascade="all, delete-orphan"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_projects_status", "status"),
        Index("idx_projects_mode", "mode"),
        Index("idx_projects_category", "category"),
        Index("idx_projects_created_at", "created_at"),
        Index("idx_projects_default_sop", "default_sop_id"),
    )

    # === GitHub + lokale Verfuegbarkeit (User-Direktive 24.06.2026) ===
    # Wird fuer die Status-Seite (PG-071-STATUS) genutzt, um zu zeigen welche
    # Projekte lokal verfuegbar sind und wo (Verzeichnis oder Container).
    github_url: Mapped[Optional[str]] = mapped_column(String(500))
    local_path: Mapped[Optional[str]] = mapped_column(String(500))
    container_name: Mapped[Optional[str]] = mapped_column(String(200))
    local_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Container-Info (User-Direktive 24.06.2026): Docker-Image + externer Port
    container_image: Mapped[Optional[str]] = mapped_column(String(200))
    container_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    container_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Kritische Findings aus Code-Review (CRIT-XX) als JSON
    critical_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # GitHub Live-Daten (User-Direktive 24.06.2026)
    github_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    github_forks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    github_default_branch: Mapped[Optional[str]] = mapped_column(String(64))
    github_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    github_size_kb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    github_license: Mapped[Optional[str]] = mapped_column(String(64))
    github_topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-Array
    github_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    github_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_stars_label: Mapped[Optional[str]] = mapped_column(String(32))
    github_language: Mapped[Optional[str]] = mapped_column(String(64))

    def __repr__(self) -> str:
        return f"<Project {self.id[:8]} '{self.name}' mode={self.mode}>"
