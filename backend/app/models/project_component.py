"""ProjectComponent-Model (User-Direktive 24.06.2026: SMproducer-Konsolidierung).

Eine Component gehoert zu einem Projekt und repraesentiert einen logischen
Bereich (Pipeline, Frontend, NotebookLM, Infra, Database, ...). Sie wird
fuer das automatische Task-Routing verwendet (siehe auto_component_router.py
und tasks.component_id Foreign-Key).

Tabelle wird per Raw-SQL-Migration angelegt (siehe restructure_smproducer.py /
backend/migrations/). Hier nur das SQLAlchemy-Mapping, damit die FK-Aufloesung
bei INSERT in tasks.component_id funktioniert.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base

if TYPE_CHECKING:
    from .project import Project
    from .task import Task


class ProjectComponent(Base):
    """Eine logische Component innerhalb eines Projekts.

    Beispiele (slug): pipeline, frontend, notebooklm, infra, database.
    """
    __tablename__ = "project_components"
    __table_args__ = (
        Index("idx_project_components_project", "project_id"),
    )

    # === Primary Key ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === Foreign Key ===
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # === Felder ===
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    component_type: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # === Container-Metadaten (optional) ===
    container_image: Mapped[Optional[str]] = mapped_column(String(200))
    container_port: Mapped[Optional[int]] = mapped_column(Integer)
    container_status: Mapped[Optional[str]] = mapped_column(String(32))
    container_name: Mapped[Optional[str]] = mapped_column(String(200))

    # === Pfade / Repos ===
    local_path: Mapped[Optional[str]] = mapped_column(String(500))
    github_url: Mapped[Optional[str]] = mapped_column(String(500))

    # === Sortierung / Timestamps ===
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === Relationships ===
    project: Mapped["Project"] = relationship("Project", back_populates="components")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="component")