"""TaskTransition-Model — Zentrale Performance-Tabelle fuer Status-Wechsel.

User-Direktive 15.06.2026:
  Jeder Status-Wechsel eines JEDEN Tasks soll zentral dokumentiert werden
  mit Projekt-ID, Timestamps, from-Status, to-Status, Verarbeitungs-Delay.

  Zusaetzlich: 5-Sekunden-Verzoegerung zwischen Status-Wechsel und
  Weiterverarbeitung (Auto-Claim, Watchdog, ...), damit der User-Prozess
  visuell sichtbar ist.

Felder:
  - id              : PK
  - task_id         : FK -> tasks.id
  - project_id      : FK -> projects.id (denormalisiert fuer schnelle Queries)
  - from_status     : alter Status (kann '' fuer initial sein)
  - to_status       : neuer Status
  - transition_at   : WANN der Wechsel angefordert wurde (HTTP-Request)
  - processing_at   : WANN die Verarbeitung tatsaechlich startet (nach Delay)
  - completed_at    : WANN die Verarbeitung abgeschlossen ist
  - delay_s         : konfigurierter Delay in Sekunden (default 5.0)
  - duration_ms     : Verarbeitungsdauer in Millisekunden
  - agent           : Wer hat den Wechsel ausgeloest (system/user/CIO/...)
  - reason          : Warum (cio_approved, auto_claim, watchdog, ...)
  - details         : JSON mit Event-spezifischen Daten

Diese Tabelle ergaenzt `task_history` (dokumentiert ALLE Events)
und spezialisiert sich auf den Lebenszyklus (Status-Transitions).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from .task import JSONType


class TaskTransition(Base):
    """Eine Status-Transition eines Tasks.

    Wird beim JEDEN Status-Wechsel angelegt (insert) und spaeter
    aktualisiert (update), sobald die Verarbeitung startet + abschliesst.
    """
    __tablename__ = "task_transitions"

    # === Primary Key ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === Foreign Keys ===
    task_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    # === Status-Transition ===
    from_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)

    # === Zeitstempel ===
    # transition_at: wann der Wechsel angefordert wurde (z.B. HTTP-Request)
    transition_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # processing_at: wann die Verarbeitung nach Delay tatsaechlich startet
    processing_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # completed_at: wann die Verarbeitung abgeschlossen ist
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Delay-Konfiguration ===
    delay_s: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)

    # === Verarbeitungs-Dauer in Millisekunden ===
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # === Kontextuelle Felder ===
    # (Session-ID, Agent, Reason, Details)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    agent: Mapped[Optional[str]] = mapped_column(String(64))
    reason: Mapped[Optional[str]] = mapped_column(String(128))
    details: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Indizes fuer Performance-Queries ===
    __table_args__ = (
        Index("idx_transition_task", "task_id"),
        Index("idx_transition_project", "project_id"),
        Index("idx_transition_project_at", "project_id", "transition_at"),
        Index("idx_transition_task_at", "task_id", "transition_at"),
        Index("idx_transition_to_status", "to_status"),
        Index("idx_transition_from_status", "from_status"),
        Index("idx_transition_at", "transition_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskTransition #{self.id} task={self.task_id[:8] if self.task_id else '?'} "
            f"{self.from_status!r}->{self.to_status!r} at={self.transition_at}>"
        )

    def to_dict(self) -> dict:
        """Serialisierung fuer API-Response."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "transition_at": self.transition_at.isoformat() if self.transition_at else None,
            "processing_at": self.processing_at.isoformat() if self.processing_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "delay_s": self.delay_s,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "agent": self.agent,
            "reason": self.reason,
            "details": self.details or {},
        }
