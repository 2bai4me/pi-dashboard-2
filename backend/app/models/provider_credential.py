"""ProviderCredential — zentrale Verwaltung von Provider-API-Keys und -Modellen."""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from decimal import Decimal

from ..db.base import Base


def _gen_id() -> str:
    """12-stellige Hex-ID fuer Credentials."""
    return secrets.token_hex(6)


class ProviderCredential(Base):
    """Ein API-Key/Base-URL-Paar fuer einen bestimmten Provider und ein Modell.

    Wird von Provider-Profilen referenziert, um Rollen auf Modelle abzubilden.
    """

    __tablename__ = "provider_credentials"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)

    # === Felder ===
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text)
    base_url: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # === Kosten (USD pro 1M Token) ===
    input_cost_per_1m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    output_cost_per_1m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_provider_credentials_provider", "provider"),
        Index("idx_provider_credentials_active", "is_active"),
        Index("idx_provider_credentials_label", "label"),
    )

    def __repr__(self) -> str:
        return f"<ProviderCredential {self.id[:8]} '{self.label}' ({self.provider}/{self.model})>"
