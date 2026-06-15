"""TokenUsage-Model — Performance-Daten fuer Analytics.

Wichtig: Trennt die Roh-Token-Counts (pro History-Eintrag) von
aggregierten Auswertungen. Erlaubt SQL-Queries wie:
- "Was war der teuerste Task letzte Woche?"
- "Wieviele Tokens pro Provider/Model?"
- "Cost-per-Role pro Tag?"
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime, Integer, BigInteger, ForeignKey, Numeric, Index
from sqlalchemy.dialects.sqlite import INTEGER as SQLiteInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base

if TYPE_CHECKING:
    from .task import Task
    from .history import TaskHistory


class TokenUsage(Base):
    """Ein Token-Usage-Record (Performance-Datenpunkt)."""
    __tablename__ = "token_usage"

    # === Primary Key ===
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(SQLiteInteger(), "sqlite"),
        primary_key=True, autoincrement=True
    )

    # === Foreign Keys (optional) ===
    task_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    history_id: Mapped[Optional[int]] = mapped_column(
        BigInteger().with_variant(SQLiteInteger(), "sqlite"),
        ForeignKey("task_history.id", ondelete="SET NULL")
    )

    # === LLM-Identifikation ===
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(64))

    # === Tokens + Cost ===
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)

    # === Pricing-Snapshot (warum genau dieser Preis?) ===
    input_per_1m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    output_per_1m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    pricing_source: Mapped[Optional[str]] = mapped_column(String(255))
    snapshot_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Timestamp ===
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # === Relations ===
    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="token_usages")
    history_entry: Mapped[Optional["TaskHistory"]] = relationship("TaskHistory")

    # === Indizes fuer Analytics ===
    __table_args__ = (
        Index("idx_token_task_id", "task_id"),
        Index("idx_token_model", "model"),
        Index("idx_token_provider", "provider"),
        Index("idx_token_role", "role"),
        Index("idx_token_recorded_at_desc", "recorded_at"),
        Index("idx_token_task_recorded", "task_id", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<TokenUsage #{self.id} {self.provider}/{self.model} in={self.tokens_in} out={self.tokens_out} ${self.cost_usd}>"
