"""Improvement-Modelle — Schwachstellen + Subagent-Analysen
User-Direktive 17.06.2026 (Prio 90 Feature)
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


def _gen_id() -> str:
    """Erzeugt eine eindeutige ID (Base32-artige 12-stellige ID)."""
    import secrets
    return secrets.token_hex(6)  # 12-stellige hex-ID


class Weakness(Base):
    """Eine erkannte Schwaechstelle im System.

    User / Sub-Agent dokumentiert sie hier. Beim Anlegen startet automatisch
    eine Analyse durch einen Sub-Agent (LLM).
    """
    __tablename__ = "improvements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # === Projekt-Pflicht (User-Direktive 17.06.2026) ===
    # Wenn die Schwachstelle als Task uebernommen wird, soll sie im richtigen
    # Projekt/Board landen. project_id ist daher NICHT optional.
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")  # low|medium|high|critical
    category: Mapped[str] = mapped_column(String(64), default="other")  # bug|ui|perf|security|arch|other
    status: Mapped[str] = mapped_column(String(16), default="analyzing")  # analyzing|done|failed|reviewed
    created_by: Mapped[str] = mapped_column(String(64), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship zu Analysen
    analyses: Mapped[List["WeaknessAnalysis"]] = relationship(
        back_populates="weakness", cascade="all, delete-orphan"
    )

    def to_dict(self, include_analyses: bool = True) -> dict:
        out = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "project_id": self.project_id,
            "severity": self.severity,
            "category": self.category,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_analyses:
            out["analyses"] = [a.to_dict() for a in self.analyses]
        return out


class WeaknessAnalysis(Base):
    """Analyse einer Schwaechstelle durch einen Sub-Agent (LLM).

    Wird automatisch beim Anlegen einer Weakness erstellt.
    Status: analyzing -> done | failed
    """
    __tablename__ = "improvement_analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)
    weakness_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("improvements.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(64), default="minimax-direct/minimax-m3")
    # === Subagent-Analyse-Felder ===
    root_cause: Mapped[str] = mapped_column(Text, default="")  # Ursachenanalyse
    solution_proposal: Mapped[str] = mapped_column(Text, default="")  # Loesungsvorschlag
    # === Optionale Editier-Historie (JSON) ===
    edit_history: Mapped[str] = mapped_column(Text, default="[]")  # JSON-Array
    status: Mapped[str] = mapped_column(String(16), default="analyzing")  # analyzing|done|failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    weakness: Mapped["Weakness"] = relationship(back_populates="analyses")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "weakness_id": self.weakness_id,
            "model": self.model,
            "root_cause": self.root_cause,
            "solution_proposal": self.solution_proposal,
            "edit_history": json.loads(self.edit_history) if self.edit_history else [],
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }
