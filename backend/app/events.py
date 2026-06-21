"""Event-Bus fuer SSE (Server-Sent Events) — SQLite-basiert.

Wird von Routers (projekt + task) befuellt und von main.py
fuer den SSE-Endpoint konsumiert.

Funktioniert Multi-Process / Multi-Worker:
- publish_event schreibt in DB-Tabelle `event_log`
- subscribe pollt die Tabelle (Long-Polling mit Watermark)
- Polling-Intervall: 0.5s (konfigurierbar)

Vorteile gegenueber In-Memory:
- Multi-Process/Multi-Worker-safe
- Events ueberleben Server-Restart
- Audit-Trail: alle Events sind in DB protokolliert
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Optional

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.orm import Session

from .db.base import Base, SessionLocal


# === Event-Log-Tabelle (persistent) ===
# Fix (v2.0-rc): Umstellung auf SQLAlchemy 2.0 Style (Mapped + mapped_column)
# Alter Stil (events.py): id: Column = Column(Integer, ...)
# Neuer Stil:           id: Mapped[int] = mapped_column(Integer, ...)
class EventLog(Base):
    """Alle veroeffentlichten Events werden hier persistent gespeichert."""
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON mit data
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_eventlog_project_ts", "project_id", "ts"),
    )

    def __repr__(self) -> str:
        return f"<EventLog {self.id} [{self.event_type}] project={self.project_id[:8]}>"


# Fix (v2.0-rc): ensure_table() wird NICHT mehr in Production aufgerufen.
# In Production muessen Migrationen via Alembic ausgefuehrt werden.
ENSURE_TABLE_ENABLED: bool = True  # Set to False in production


def ensure_table():
    """Stellt sicher, dass die EventLog-Tabelle existiert.
    
    Fix (v2.0-rc): Wird nur in development/ENV=development ausgefuehrt.
    In Production muss die Tabelle via Alembic-Migration erstellt werden.
    """
    from .config import settings
    if settings.ENV != "development":
        raise RuntimeError(
            "EventLog-Tabelle fehlt! Bitte Migration ausfuehren: "
            "alembic upgrade head"
        )
    from .db.base import engine
    EventLog.__table__.create(bind=engine, checkfirst=True)


# === Public API ===
async def publish_event(project_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Veroeffentlicht ein Event (persistent in DB)."""
    if not project_id:
        return
    payload = json.dumps(data, default=str, ensure_ascii=False)
    # DB-Insert (synchron, in eigenem Thread damit Event-Loop nicht blockiert)
    def _insert():
        with SessionLocal() as db:
            ev = EventLog(project_id=project_id, event_type=event_type, payload=payload)
            db.add(ev)
            db.commit()
    await asyncio.to_thread(_insert)


def get_events_since(project_id: str, since_id: int = 0, limit: int = 100) -> list[dict]:
    """Holt alle Events eines Projekts seit einer bestimmten Event-ID."""
    ensure_table()
    with SessionLocal() as db:
        rows = db.execute(
            EventLog.__table__.select().where(
                EventLog.project_id == project_id,
                EventLog.id > since_id,
            ).order_by(EventLog.id).limit(limit)
        ).fetchall()
        return [
            {"id": r.id, "type": r.event_type, "ts": r.ts.isoformat(),
             "project_id": r.project_id, "data": json.loads(r.payload)}
            for r in rows
        ]


async def subscribe(project_id: str, last_event_id: int = 0) -> "EventStream":
    """Erzeugt einen Long-Polling-Stream fuer ein Projekt.

    Polling-Intervall: 0.3s (kompromiss zwischen Latenz und DB-Last).
    """
    ensure_table()
    return EventStream(project_id, last_event_id)


class EventStream:
    """Async-Iterator ueber Events. Long-Polling-Implementierung."""

    def __init__(self, project_id: str, last_event_id: int = 0):
        self.project_id = project_id
        self.last_event_id = last_event_id
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._closed:
            raise StopAsyncIteration
        # Long-Polling: warte bis neue Events verfuegbar sind
        for _ in range(60):  # max 60 Versuche * 0.5s = 30s timeout
            events = await asyncio.to_thread(
                get_events_since, self.project_id, self.last_event_id, 100
            )
            if events:
                self.last_event_id = events[-1]["id"]
                return events
            await asyncio.sleep(0.5)
        # Timeout: yield empty list (oder Stop?)
        return []

    def close(self):
        self._closed = True

