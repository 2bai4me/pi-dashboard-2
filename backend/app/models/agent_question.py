"""AgentQuestion-Model: Interaktions-Tool fuer User <-> Agent.

Ermoeglicht es Agenten jeder Ebene (C-Level, Worker, Subagent) Rueckfragen
an den User zu stellen und vom User Texte, Dateien oder Bilder als Antwort
zu erhalten.

Einsatzszenarien:
- Agent braucht Input vom User (z.B. "Welche Datenbank-URL?")
- Agent moechte ein Bild vom User (z.B. Screenshot eines Bugs)
- Agent moechte eine Bestaetigung (z.B. "Soll ich wirklich loeschen?")
- Agent hat einen Anhang, den der User pruefen soll

User-Direktive 17.06.2026.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Any

from sqlalchemy import String, Text, DateTime, Integer, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .task import JSONType
from ..db.base import Base

if TYPE_CHECKING:
    from .agent_question import AgentQuestionAttachment


def _gen_id() -> str:
    """Eindeutige 12-stellige ID fuer Fragen."""
    return f"q-{secrets.token_hex(6)}"


class AgentQuestion(Base):
    """Eine offene/beantwortete Frage eines Agenten an den User.

    Status:
      pending   = offen, wartet auf User-Antwort
      answered  = User hat geantwortet
      cancelled = Agent hat storniert (z.B. weil obsolete)
      expired   = Timeout ueberschritten, ohne Antwort
    """
    __tablename__ = "agent_questions"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)

    # === Agent-Identifikation ===
    # agent_id: technische ID (z.B. "pi-coder-001", "cio", "main-agent")
    # agent_level: Hierarchie-Ebene
    #   - "C-Level"   = CIO, CEO-digital
    #   - "Worker"    = pi-coder, pi-tester, pi-reviewer, pi-fixer
    #   - "Subagent"  = swarm-spawner-Subagent
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_level: Mapped[str] = mapped_column(String(16), nullable=False, default="Worker")
    agent_label: Mapped[Optional[str]] = mapped_column(String(128))

    # === Frage ===
    # question_type:
    #   - "text"          = freie Texteingabe
    #   - "confirmation"  = ja/nein Bestaetigung
    #   - "choice"        = Single-Choice aus Optionen
    #   - "attachment"    = Anhang erforderlich
    #   - "image"         = Bild erforderlich (z.B. Screenshot)
    #   - "any"           = freie Antwort (Text + Anhang + Bild)
    question_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)  # zusaetzlicher Kontext zur Frage
    recommendation: Mapped[Optional[str]] = mapped_column(Text)  # vom Agent vorgeschlagene Antwort
    options: Mapped[Optional[list]] = mapped_column(JSONType, default=list)  # fuer question_type=choice

    # === Kontext ===
    # context enthaelt z.B. task_id, project_id, subagent_run_id, step_info
    context: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Options-Config (User-Direktive 17.06.2026) ===
    # Welche Felder werden im Dialog angezeigt / sind editierbar?
    # Beispiel:
    # {
    #   "show_description": true,
    #   "show_recommendation": true,
    #   "show_tts": true,
    #   "allow_edit_recommendation": true,
    #   "answer_required": true,
    #   "recommendation_as_default": true
    # }
    options_config: Mapped[Optional[str]] = mapped_column(Text)  # JSON

    # === Antwort-Attachments (Pfade, JSON) ===
    # Liste der Attachment-IDs, die der User seiner Antwort beigefuegt hat
    answer_attachments: Mapped[Optional[str]] = mapped_column(Text)  # JSON

    # === Status / Prioritaet ===
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    # priority: low | medium | high | urgent
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)

    # === Antwort (vom User) ===
    answer_text: Mapped[Optional[str]] = mapped_column(Text)
    answer_choice: Mapped[Optional[str]] = mapped_column(String(500))  # bei question_type=choice
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[Optional[str]] = mapped_column(String(64))

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Notification-Ack (User hat gesehen) ===
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Relations ===
    attachments: Mapped[List["AgentQuestionAttachment"]] = relationship(
        "AgentQuestionAttachment",
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_aq_agent_id", "agent_id"),
        Index("idx_aq_status", "status"),
        Index("idx_aq_priority", "priority"),
        Index("idx_aq_created_at", "created_at"),
        Index("idx_aq_agent_status", "agent_id", "status"),
    )

    def to_dict(self, include_attachments: bool = False) -> dict:
        """Serialisiert das Objekt fuer API-Responses."""
        import json as _json
        opts = {}
        if self.options_config:
            try:
                opts = _json.loads(self.options_config)
            except Exception:
                opts = {}
        atts: list[str] = []
        if self.answer_attachments:
            try:
                atts = _json.loads(self.answer_attachments)
            except Exception:
                atts = []
        d: dict[str, Any] = {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_level": self.agent_level,
            "agent_label": self.agent_label,
            "question_type": self.question_type,
            "title": self.title,
            "question": self.question,
            "description": self.description,
            "recommendation": self.recommendation,
            "options": self.options or [],
            "options_config": opts,
            "context": self.context or {},
            "status": self.status,
            "priority": self.priority,
            "answer_text": self.answer_text,
            "answer_choice": self.answer_choice,
            "answer_attachments": atts,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
            "answered_by": self.answered_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "seen_at": self.seen_at.isoformat() if self.seen_at else None,
            "attachment_count": len(self.attachments) if self.attachments else 0,
        }
        if include_attachments and self.attachments:
            d["attachments"] = [a.to_dict() for a in self.attachments]
        return d


class AgentQuestionAttachment(Base):
    """Ein Anhang zu einer AgentQuestion (Datei oder Bild)."""
    __tablename__ = "agent_question_attachments"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True,
                                    default=lambda: f"att-{secrets.token_hex(6)}")

    # === Foreign Key ===
    question_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_questions.id", ondelete="CASCADE"), nullable=False
    )

    # === File-Info ===
    # kind: "file" (generischer Anhang) | "image" (Bild, wird im UI angezeigt) | "user_file" (Antwort-Datei vom User)
    kind: Mapped[str] = mapped_column(String(16), default="file", nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # relativ zu UPLOAD_DIR
    mime_type: Mapped[Optional[str]] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # === Source: agent (vom Agent angehaengt) | user (Antwort-Anhang vom User) ===
    source: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)

    # === Timestamps ===
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # === Relations ===
    question: Mapped["AgentQuestion"] = relationship(
        "AgentQuestion", back_populates="attachments"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_aqa_question_id", "question_id"),
    )

    def to_dict(self) -> dict:
        """Serialisiert fuer API-Responses (ohne file_path-Internas)."""
        return {
            "id": self.id,
            "question_id": self.question_id,
            "kind": self.kind,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "source": self.source,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }
