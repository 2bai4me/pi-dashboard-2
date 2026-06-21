"""Tests zur Sicherstellung, dass API-Keys/Secrets nicht im Repo liegen."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from app.config import BACKEND_ROOT, Settings
from app.services import llm_service


class TestLLMServiceSecrets:
    """Sicherheits-Tests fuer llm_service."""

    def test_load_api_credentials_returns_empty_when_key_missing(self, monkeypatch):
        """Wenn MINIMAX_API_KEY nicht gesetzt ist, liefert _load_api_credentials einen leeren Key."""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.setattr(llm_service, "DEFAULT_API_KEY", "")

        api_key, base_url = llm_service._load_api_credentials()
        assert api_key == ""
        assert base_url == llm_service.DEFAULT_BASE_URL

    def test_chat_openai_compatible_raises_without_key(self, monkeypatch):
        """chat_completion muss bei fehlendem Key abbrechen (kein models.json-Fallback)."""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.setattr(llm_service, "DEFAULT_API_KEY", "")

        async def _run():
            return await llm_service._chat_openai_compatible(
                messages=[{"role": "user", "content": "Hi"}],
                model="minimax-m3",
                temperature=0.3,
                max_tokens=100,
                response_format=None,
                timeout_sec=5.0,
            )

        with pytest.raises(RuntimeError, match="API-Key nicht gesetzt"):
            asyncio.run(_run())


class TestModelsJSONSecrets:
    """Sicherheits-Tests fuer models.json."""

    def test_models_json_contains_no_api_keys(self):
        """models.json darf keine apiKey-Felder mehr enthalten."""
        models_path = BACKEND_ROOT / "models.json"
        assert models_path.exists(), "models.json nicht gefunden"

        with open(models_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        providers = data.get("providers", {})
        assert providers, "Keine Provider in models.json gefunden"

        for provider_name, provider_config in providers.items():
            assert "apiKey" not in provider_config, (
                f"Provider '{provider_name}' enthaelt noch ein apiKey-Feld"
            )


class TestAuthSecretsValidation:
    """Tests fuer die Auth-Secret-Validierung."""

    def test_auth_enabled_requires_secure_jwt_secret(self, monkeypatch):
        """Bei AUTH_ENABLED=true muss ein sicheres JWT_SECRET gesetzt sein."""
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("JWT_SECRET", "__CHANGE_ME__")
        monkeypatch.setenv("ADMIN_PASSWORD", "secure-password")

        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings()

    def test_auth_enabled_accepts_secure_admin_password(self, monkeypatch):
        """Bei AUTH_ENABLED=true und sicherem JWT_SECRET/Passwort startet die Konfiguration."""
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("JWT_SECRET", "super-secret-jwt-key-32-chars-long")
        monkeypatch.setenv("ADMIN_PASSWORD", "secure-admin-password")

        settings = Settings()
        assert settings.AUTH_ENABLED is True
        assert settings.JWT_SECRET == "super-secret-jwt-key-32-chars-long"
