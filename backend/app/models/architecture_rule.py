"""ArchitectureRule-Model (Standardvorgaben persistent).

User-Direktive 16.06.2026: "Im SOP muessen die Aufgaben des Agenten genauer
beschrieben werden ... der CIO prüft ob die Anforderung den Standard-Vorgaben
fuer unsere Entwicklung entspricht, was im OpenBrain als solches festgelegt
wurden."

Damit der CIO das strukturiert pruefen kann, werden die Standardvorgaben
persistent in der DB gespeichert (architecture_rules). Defaults werden
aus dem OpenBrain uebernommen (siehe Migration d4e5f6a7b8c9).

Beispiele:
  - arch-soa: "Alles wird im Architektur-Geiste von SOA entwickelt"
  - arch-microservices: "Jeder Service besteht aus Microservices"
  - arch-fastapi: "Python 3.11+ / FastAPI als Backend-Standard"
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base


class ArchitectureRule(Base):
    """Eine Standardvorgabe fuer die Entwicklung.

    Wird vom CIO im SOP-Schritt 0 (Triage Review) referenziert.
    Default-Seed kommt aus dem OpenBrain.
    """
    __tablename__ = "architecture_rules"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Identifikation ===
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # === Quelle ===
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="openbrain")
    # source: "openbrain" | "url" | "hardcoded" | "user"
    source_ref: Mapped[Optional[str]] = mapped_column(String(255))
    # source_ref: z.B. "openbrain-tag:SOA" oder "https://wiki.example.com/standards"

    # === Kategorie ===
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="architecture", index=True)
    # category: "architecture" | "security" | "style" | "process" | "data"

    # === Schwere (severity) ===
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="should")
    # severity: "must" (PFLICHT) | "should" (EMPFOHLEN) | "may" (OPTIONAL)

    # === Status ===
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_arch_rules_category_active", "category", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ArchitectureRule {self.id} '{self.name}' {self.severity}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "source_ref": self.source_ref,
            "category": self.category,
            "severity": self.severity,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
