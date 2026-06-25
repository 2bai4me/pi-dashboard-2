"""ProjectInfo-Model (User-Direktive 24.06.2026, Grill-Me-Skill).

Ein fortlaufend gepflegtes Informationspaket pro Projekt, das der Grill-Me Analyst
und andere SubAgents nutzen, um die richtigen Fragen zu stellen und
fundierte Entscheidungen zu treffen.

Typen:
  - architecture: Komponenten, Datenflüsse, APIs
  - conventions: Code-Style, Naming, Formatierung
  - dependencies: Wichtige Libraries/Frameworks/Versionen
  - components: Sub-Module und ihre Verantwortlichkeiten
  - contacts: Ansprechpartner, Verantwortliche
  - risks: Bekannte Probleme, Limitierungen
  - decisions: Architektur-Entscheidungen (ADRs light)
  - context: User-spezifischer Kontext (z.B. Workflow-Präferenzen)
  - domain: Fachwissen (Begriffe, Konzepte)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base


class ProjectInfoEntry(Base):
    """Ein einzelner Info-Eintrag im Projekt-Informationspaket."""
    __tablename__ = "project_info_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    info_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    info_key: Mapped[str] = mapped_column(String(100), nullable=False)
    info_value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    # source: "manual" | "agent" | "auto" | "grill-me"
    confidence: Mapped[float] = mapped_column(Integer, default=100, nullable=False)
    # 0-100, wie sicher ist sich der Eintrag
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )