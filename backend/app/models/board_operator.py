"""BoardOperator-Model: Eigenstaendige Watchdog-Instanz pro Live-Board.

User-Direktive 17.06.2026:
  Wenn ein Board auf mode=live steht, wird automatisch ein
  BoardOperator als eigenstaendige asyncio-Task gestartet.
  Nur wenn dieser Operator aktiv ist (Heartbeat < 15s alt),
  wird das Live-Icon GRUEN dargestellt.

Aufgabe:
  - Permanente Ueberwachung aller Tasks in dem Board
  - Erkennung haengender Tasks (in_progress ohne Update > X min)
  - Erkennung nicht-beantworteter Rueckfragen (> X min)
  - Meldung ueber AgentQuestion-Tool an User
  - Auto-Triage / Auto-Reopen wo sinnvoll
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base


def _gen_id() -> str:
    return f"op-{secrets.token_hex(6)}"


class BoardOperator(Base):
    """Eine Watchdog-Instanz fuer ein Live-Board.

    Eine Instanz pro Board (1:1 zu projects.id).
    Wird automatisch gestartet wenn mode=live,
    automatisch gestoppt wenn mode != live.
    """
    __tablename__ = "board_operators"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)

    # === Foreign Key (1:1 zu projects) ===
    board_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    # === Status ===
    # not_started | starting | active | stale | stopped | error
    agent_status: Mapped[str] = mapped_column(
        String(16), default="not_started", nullable=False, index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # === Lifecycle ===
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Watchdog-Stats ===
    checks_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stale_tasks_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions_asked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # === Config (optional, per Board ueberschreibbar) ===
    # JSON-String mit Schwellwerten:
    # {"stale_minutes": 30, "check_interval_s": 30, "alert_on_stale": true}
    config_json: Mapped[Optional[str]] = mapped_column(Text)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_bo_status", "agent_status"),
        Index("idx_bo_heartbeat", "last_heartbeat"),
    )

    def __repr__(self) -> str:
        return f"<BoardOperator {self.id[:8]} board={self.board_id[:8]} status={self.agent_status}>"

    def to_dict(self) -> dict:
        """Serialisiert fuer API-Responses."""
        from datetime import timezone
        now = datetime.utcnow()
        last_hb_age_s = None
        if self.last_heartbeat:
            # both stored as UTC; compute naive diff (SQLite stores naive)
            last_hb_naive = self.last_heartbeat.replace(tzinfo=None) if self.last_heartbeat.tzinfo else self.last_heartbeat
            now_naive = now.replace(tzinfo=None) if now.tzinfo else now
            last_hb_age_s = int((now_naive - last_hb_naive).total_seconds())

        # Live-Indikator:
        #   active (Heartbeat < 15s)        -> gruen
        #   stale  (Heartbeat 15-60s)       -> gelb
        #   dead   (Heartbeat > 60s / none) -> rot
        #   not_started / starting          -> grau
        #   stopped / error                 -> ausgegraut
        if self.agent_status in ("active",):
            if last_hb_age_s is None or last_hb_age_s > 60:
                live_color = "red"
                live_label = "dead"
            elif last_hb_age_s > 15:
                live_color = "yellow"
                live_label = "stale"
            else:
                live_color = "green"
                live_label = "active"
        elif self.agent_status in ("starting",):
            live_color = "gray"
            live_label = "starting"
        elif self.agent_status in ("stale",):
            live_color = "yellow"
            live_label = "stale"
        elif self.agent_status in ("error",):
            live_color = "red"
            live_label = "error"
        else:
            live_color = "gray"
            live_label = "inactive"

        return {
            "id": self.id,
            "board_id": self.board_id,
            "agent_status": self.agent_status,
            "live_color": live_color,
            "live_label": live_label,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_heartbeat_age_s": last_hb_age_s,
            "checks_total": self.checks_total,
            "stale_tasks_found": self.stale_tasks_found,
            "alerts_sent": self.alerts_sent,
            "questions_asked": self.questions_asked,
            "error_message": self.error_message,
        }
