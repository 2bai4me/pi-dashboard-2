"""Brainstorming-Model — Brainstorming-Log pro Projekt."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base


class BrainstormEntry(Base):  # type: ignore
    """Ein einzelner Brainstorming-Turn."""
    __tablename__ = "brainstorm_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' | 'assistant'
    text: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="input", nullable=False)  # input | clarifying | summary
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_brainstorm_project", "project_id"),
        Index("idx_brainstorm_ts", "ts"),
    )


class RequirementDoc(Base):  # type: ignore
    """Anforderungs-Dokument pro Projekt."""
    __tablename__ = "requirement_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)  # draft | review | approved | rejected
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    review_score: Mapped[Optional[float]] = mapped_column(nullable=True)  # NALABS-Score 0-100
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_reqdoc_project", "project_id"),
        Index("idx_reqdoc_status", "status"),
    )


class ReviewPipeline(Base):  # type: ignore
    """9-Schritte-Review-Pipeline pro Requirement-Doc."""
    __tablename__ = "review_pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    doc_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("requirement_docs.id", ondelete="SET NULL"))
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)  # z.B. 'zielgruppen_check', 'redundancy_check'
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-8
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending | running | done | failed
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-Output
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_review_project", "project_id"),
        Index("idx_review_status", "status"),
    )


class ImplementationStep(Base):  # type: ignore
    """Implementation-Plan (3 Phasen, mehrere Steps)."""
    __tablename__ = "implementation_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-N innerhalb der Phase
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending | in_progress | done | skipped
    cio_approved: Mapped[bool] = mapped_column(default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_impl_project", "project_id"),
        Index("idx_impl_phase", "phase"),
    )
