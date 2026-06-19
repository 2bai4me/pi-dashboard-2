"""TaskDraft Model — Iterativer Task-Refinement-Workflow (User-Direktive 18.06.2026).

Workflow:
  1. User beschreibt Task (kurze Notiz)
  2. KI generiert vollstaendigen Task-Entwurf (Title, Description, success_criteria, priority, ...)
  3. User passt an (edit einen Wert, fuegt Anforderung hinzu, ...)
  4. KI optimiert auf Basis des User-Feedbacks
  5. ... (Schritte 3+4 koennen mehrfach wiederholt werden)
  6. User klickt "Freigeben" -> echter Task wird erstellt (status=triage, SOP-Engine laeuft)

Speicherung:
  - id:           Eindeutige Draft-ID (z.B. "draft-abc12345")
  - user_input:   Original-User-Beschreibung
  - current:      Aktueller Stand des Entwurfs (JSON: title, description, ...)
  - iterations:   Liste aller Iterationen [{user_input, ai_output, timestamp}]
  - status:       'draft' | 'published' | 'abandoned'
  - final_task_id: Task-ID nach Publish
  - created_at, updated_at
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class TaskDraft(Base):
    """Ein iterativer Task-Entwurf im User<->KI Workflow."""
    __tablename__ = "task_drafts"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === User-Input (Original-Beschreibung) ===
    user_input: Mapped[str] = mapped_column(String(2000), nullable=False)

    # === Aktueller Stand des Entwurfs (JSON) ===
    # Struktur: {
    #   "title": str,
    #   "description": str,
    #   "priority": int (1-100),
    #   "category": str,
    #   "success_criteria": List[str],
    #   "assigned_role": str,
    #   "project_id": str,
    #   "tags": List[str],
    #   "acceptance_criteria_explanation": str
    # }
    current: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # === Iterations-History ===
    # Liste: [
    #   {iteration: 1, user_input: "...", ai_output: {...}, timestamp: "..."},
    #   {iteration: 2, user_input: "...", ai_output: {...}, timestamp: "..."}
    # ]
    iterations: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # === Status ===
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    # Werte: 'draft' | 'published' | 'abandoned'

    # === Final Task ID (nach Publish) ===
    final_task_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # === Indizes ===
    __table_args__ = (
        Index("idx_task_drafts_status", "status"),
        Index("idx_task_drafts_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TaskDraft {self.id[:12]} status={self.status} iter={len(self.iterations)}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_input": self.user_input,
            "current": self.current,
            "iterations": self.iterations,
            "status": self.status,
            "final_task_id": self.final_task_id,
            "iteration_count": len(self.iterations),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
