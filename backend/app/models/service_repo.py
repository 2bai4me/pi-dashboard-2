"""ExternalServiceRepo-Model (User-Direktive 24.06.2026).

Verwandte Service-Repos, die NICHT in der operativen Project-Tabelle sind,
aber zu einem Hauptprojekt gehoeren (z.B. ME4-SMproducer-3 hat mehrere
Service-Repos wie ME4-YouTube, ME4-NotebookLM, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.base import Base


class ExternalServiceRepo(Base):
    """Ein externes Service-Repository."""
    __tablename__ = "external_service_repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    local_path: Mapped[Optional[str]] = mapped_column(String(500))
    github_url: Mapped[str] = mapped_column(String(500), nullable=False)
    local_available: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
