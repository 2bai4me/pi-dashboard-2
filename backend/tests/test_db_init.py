"""Tests fuer die DB-Initialisierung (create_all nur in Development)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.db.base import Base, init_db
from app.config import settings


class TestInitDb:
    """Sicherstellen, dass init_db() in Production keine Tabellen erstellt."""

    def test_development_calls_create_all(self, monkeypatch):
        """In ENV=development muss init_db() Base.metadata.create_all() aufrufen."""
        monkeypatch.setattr(settings, "ENV", "development")

        with patch.object(Base.metadata, "create_all") as mock_create_all:
            init_db()

        mock_create_all.assert_called_once()

    def test_production_raises_when_tables_missing(self, monkeypatch):
        """In ENV=production wirft init_db() einen Fehler, wenn Tabellen fehlen."""
        monkeypatch.setattr(settings, "ENV", "production")

        fake_inspector = MagicMock()
        fake_inspector.get_table_names.return_value = []

        with patch("app.db.base.inspect", return_value=fake_inspector):
            with pytest.raises(RuntimeError) as exc_info:
                init_db()

        assert "missing database tables" in str(exc_info.value)
        assert "alembic upgrade head" in str(exc_info.value)

    def test_production_succeeds_when_tables_exist(self, monkeypatch):
        """In ENV=production laeuft init_db() durch, wenn alle Tabellen existieren."""
        monkeypatch.setattr(settings, "ENV", "production")

        # Alle erwarteten Tabellen sind bereits vorhanden
        expected_tables = list(Base.metadata.tables.keys())
        fake_inspector = MagicMock()
        fake_inspector.get_table_names.return_value = expected_tables

        with patch.object(Base.metadata, "create_all") as mock_create_all:
            with patch("app.db.base.inspect", return_value=fake_inspector):
                init_db()

        mock_create_all.assert_not_called()
