"""Role-Model — Sub-Agent + Organisationale Rollen."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base
from .task import JSONType


class Role(Base):
    """Eine Rolle (Sub-Agent pi-coder/pi-tester/etc. oder Org CIO/CEO-digital/CMO/CFO).

    Wird aus swarm-spawner/index.ts (TS-Definition) + ORG_ROLES (Python) initialisiert.
    """
    __tablename__ = "roles"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Felder ===
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Editierbarer Anzeigename (falls gesetzt, wird er statt `name` in der UI angezeigt).
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    role_type: Mapped[str] = mapped_column(String(32), default="sub_agent", nullable=False)  # sub_agent | org
    emoji: Mapped[Optional[str]] = mapped_column(String(8))  # 👑 🏗️ 📢 💰 💻 🧪 👁️ 🔧

    # === LLM-Config ===
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    api_key_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("provider_credentials.id", ondelete="SET NULL"), nullable=True
    )

    # === Prompts + Tools ===
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    tool_whitelist: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # === SOP-Zuordnung (rein informativ; beeinflusst die Prozesssteuerung NICHT) ===
    assigned_sop_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sops.id", ondelete="SET NULL"), nullable=True
    )

    # === Verhaltens-Tuning ===
    timeout_sec: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    fresh_context: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    estimated_savings_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0, nullable=False)

    # === User-Modification-Flag (User-Direktive 24.06.2026) ===
    # Wenn True: Der User hat die Rolle manuell geaendert.
    # seed_defaults() ueberschreibt sie NICHT mehr beim Startup.
    # Setzt sich automatisch zurueck, wenn der User explizit "Reset to Default" waehlt.
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Role {self.id[:8]} '{self.name}' type={self.role_type} provider={self.provider}>"

    def to_dict(self) -> dict:
        """Serialisiert die Rolle als Dict (z.B. fuer Snapshot vor Loeschung)."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "role_type": self.role_type,
            "emoji": self.emoji,
            "provider": self.provider,
            "model": self.model,
            "api_key_id": self.api_key_id,
            "assigned_sop_id": self.assigned_sop_id,
        }
