"""ModelPricing — Provider-Preise persistent in DB."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Numeric, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base


class ModelPricing(Base):
    """Provider-Preise (USD pro 1M Tokens).

    Wird beim Refresh vom Frontend (POST /api/models/pricing/refresh)
    aktualisiert. Ersetzt ~/.pi/agent/models.json fuer v2.0.
    """
    __tablename__ = "model_pricing"

    # === Primary Key ===
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # === Identifikation ===
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # === Preise (USD pro 1M Tokens) ===
    input_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    output_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)

    # === Source + Timestamp ===
    source: Mapped[Optional[str]] = mapped_column(String(255))
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # === Constraints + Indizes ===
    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_pricing_provider_model"),
        Index("idx_pricing_provider_default", "provider", "is_default"),
    )

    def __repr__(self) -> str:
        return f"<ModelPricing {self.provider}/{self.model_id} ${self.input_per_1m}/${self.output_per_1m}>"
