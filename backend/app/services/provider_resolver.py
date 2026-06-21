"""Provider-Resolver — Multi-Provider-Fähigkeit über Role → Credential.

Löst für eine Rolle den passenden Provider/Modell/API-Key/Base-URL auf.
Die Zuordnung erfolgt direkt am Role-Modell (`api_key_id` -> ProviderCredential).
Falls keine Rolle konfiguriert ist, wird auf Umgebungsvariablen zurückgegriffen.
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.base import SessionLocal
from ..models.role import Role
from ..models.provider_credential import ProviderCredential


def get_role_config(db: Session, role: str) -> Optional[dict]:
    """Liefert die Provider-Konfiguration für eine Rolle.

    Reihenfolge:
      1. Role hat `api_key_id` -> Werte aus ProviderCredential
      2. Role hat `provider`/`model` -> lokale Werte (ohne API-Key/Base-URL)
      3. Sonst None

    Returns:
        dict mit keys: provider, model, api_key, base_url
    """
    role_obj = db.execute(select(Role).where(Role.name == role)).scalar_one_or_none()
    if not role_obj:
        return None

    # 1) Referenzierte Credential bevorzugen
    if role_obj.api_key_id:
        credential = db.get(ProviderCredential, role_obj.api_key_id)
        if credential:
            return {
                "provider": credential.provider,
                "model": credential.model,
                "api_key": credential.api_key or "",
                "base_url": credential.base_url or "",
            }

    # 2) Lokale Role-Werte
    if role_obj.provider and role_obj.model:
        return {
            "provider": role_obj.provider,
            "model": role_obj.model,
            "api_key": "",
            "base_url": "",
        }

    return None


def _env_or_setting(name: str, default: str = "") -> str:
    """Liest einen Wert aus settings (Pydantic) oder os.environ."""
    value = ""
    if hasattr(settings, name):
        value = getattr(settings, name) or ""
    if not value:
        value = os.getenv(name, "")
    if not value:
        value = default
    return value


def resolve_model_config(role: Optional[str] = None) -> dict:
    """Löst die LLM-Konfiguration für eine Rolle auf.

    Reihenfolge:
      1. Role-Direktzuordnung (api_key_id -> Credential oder provider/model)
      2. Umgebungsvariablen / Settings (MINIMAX_API_KEY, KIMI_API_KEY, ...)
      3. RuntimeError, wenn nichts konfiguriert ist

    Returns:
        dict mit keys: provider, model, api_key, base_url
    """
    if role:
        with SessionLocal() as db:
            config = get_role_config(db, role)
            if config:
                return config

    # Fallback auf ENV-Variablen (Priorität: MiniMax -> Kimi -> OpenAI -> OpenRouter)
    fallbacks = [
        (
            "MINIMAX_API_KEY",
            "minimax-direct",
            "minimax-m3",
            "MINIMAX_BASE_URL",
            "https://api.minimax.io/v1",
        ),
        (
            "KIMI_API_KEY",
            "kimi",
            "kimi-default",
            "KIMI_BASE_URL",
            "https://api.moonshot.cn/v1",
        ),
        (
            "OPENAI_API_KEY",
            "openai",
            "gpt-4",
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        (
            "OPENROUTER_API_KEY",
            "openrouter",
            "openrouter/auto",
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ),
    ]

    for api_key_env, provider, model, base_url_env, default_base_url in fallbacks:
        api_key = _env_or_setting(api_key_env)
        if api_key:
            base_url = os.getenv(base_url_env, default_base_url)
            return {
                "provider": provider,
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
            }

    raise RuntimeError(
        "Keine Provider-Konfiguration für die Rolle und kein API-Key in ENV konfiguriert"
    )
