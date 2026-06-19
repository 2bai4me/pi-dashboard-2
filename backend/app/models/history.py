"""TaskHistory-Model — Vollständiges Audit-Log pro Task."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING, Any
from sqlalchemy import String, Text, DateTime, Integer, BigInteger, ForeignKey, Index, JSON, Numeric
from sqlalchemy.dialects.sqlite import INTEGER as SQLiteInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base
from .task import JSONType


class TaskHistory(Base):
    """Ein Eintrag in der Task-Historie.

    Events:
    - task_created
    - status_changed
    - priority_changed
    - auto_claim
    - operator_dispatched
    - subagent_dispatched
    - token_usage_report
    - workflow_cio_approve
    - workflow_cio_reject
    - subtask_created
    - escalated
    - revived
    """
    __tablename__ = "task_history"

    # === Primary Key ===
    # SQLite: INTEGER PRIMARY KEY AUTOINCREMENT
    # PostgreSQL: BIGSERIAL
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(SQLiteInteger(), "sqlite"),
        primary_key=True, autoincrement=True
    )

    # === Foreign Key ===
    task_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )

    # === Event-Felder ===
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    agent: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(128))

    # === Token- + Cost-Tracking (NEU: pro History-Eintrag!) ===
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)

    # === Detail-Daten (Event-spezifisch) ===
    details: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Relations ===
    task: Mapped["Task"] = relationship("Task", back_populates="history_entries")

    # === Indizes ===
    __table_args__ = (
        Index("idx_history_task_ts", "task_id", "ts"),
        Index("idx_history_event", "event"),
        Index("idx_history_agent", "agent"),
        Index("idx_history_model", "model"),
        Index("idx_history_ts_desc", "ts"),
    )

    def __repr__(self) -> str:
        return f"<TaskHistory #{self.id} task={self.task_id[:8]} event={self.event}>"
