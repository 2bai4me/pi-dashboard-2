"""Provider-Resolver — Multi-Provider-Fähigkeit über Role → Credential.

Löst für eine Rolle den passenden Provider/Modell/API-Key/Base-URL auf.
Die Zuordnung erfolgt direkt am Role-Modell (`api_key_id` -> ProviderCredential).
Falls keine Rolle konfiguriert ist, wird auf Umgebungsvariablen und anschließend
auf `~/.pi/agent/auth.json` / `models.json` zurückgegriffen (Single Source of Truth
für Provider-Keys, analog zur pi-CLI).
"""
from __future__ import annotations

import json
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings, get_auth_json_path, get_models_json_path
from ..db.base import SessionLocal
from ..models.role import Role
from ..models.provider_credential import ProviderCredential


# Werte, die als "nicht konfiguriert" behandelt werden (Platzhalter / unsicher)
_INSECURE_VALUES = {
    "",
    "__CHANGE_ME__",
    "change-me-to-a-random-32-byte-base64-secret",
    "set-a-strong-shared-key-for-external-subagents",
}

# Mapping: interner Provider-Name -> Schlüssel-Name in auth.json
_PROVIDER_TO_AUTH_KEY = {
    "minimax-direct": "minimax",
    "minimax": "minimax",
    "kimi": "kimi",
    "kimi-coding": "kimi-coding",
    "openai": "openai",
    "openrouter": "openrouter",
    "anthropic": "anthropic",
}


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


def _is_secure(value: str) -> bool:
    """Prüft, ob ein konfigurierter Wert tatsächlich gesetzt und sicher ist."""
    if not value:
        return False
    if value.strip() in _INSECURE_VALUES:
        return False
    if "__CHANGE_ME__" in value:
        return False
    return True


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


def _read_auth_json() -> dict:
    """Liest die zentrale auth.json (API-Keys)."""
    try:
        return json.loads(get_auth_json_path().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_models_json() -> dict:
    """Liest die zentrale models.json (Provider/Modell-Konfiguration)."""
    try:
        return json.loads(get_models_json_path().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"providers": {}}


def _api_key_from_auth(provider: str) -> str:
    """Sucht einen API-Key für den Provider in auth.json (inkl. Alias-Mapping)."""
    auth = _read_auth_json()
    key_name = _PROVIDER_TO_AUTH_KEY.get(provider, provider)
    entry = auth.get(key_name)
    if isinstance(entry, dict):
        return entry.get("key", "") or ""
    if isinstance(entry, str):
        return entry
    return ""


def _base_url_for_provider(provider: str, default: str) -> str:
    """Liest die Base-URL für einen Provider aus models.json."""
    cfg = _read_models_json()
    prov_cfg = (cfg.get("providers") or {}).get(provider, {})
    return prov_cfg.get("baseUrl") or prov_cfg.get("api") or default


def _resolve_fallback_config(
    api_key_env: str,
    provider: str,
    model: str,
    base_url_env: str,
    default_base_url: str,
) -> Optional[dict]:
    """Ermittelt Key/Base-URL für einen Provider aus ENV oder auth.json/models.json."""
    api_key = _env_or_setting(api_key_env)
    if not _is_secure(api_key):
        api_key = _api_key_from_auth(provider)

    if not _is_secure(api_key):
        return None

    base_url = os.getenv(base_url_env) or _base_url_for_provider(provider, default_base_url)
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


def resolve_model_config(role: Optional[str] = None) -> dict:
    """Löst die LLM-Konfiguration für eine Rolle auf.

    Reihenfolge:
      1. Role-Direktzuordnung (api_key_id -> Credential oder provider/model)
      2. Umgebungsvariablen / Settings (MINIMAX_API_KEY, KIMI_API_KEY, ...)
      3. `~/.pi/agent/auth.json` + `models.json` als Single Source of Truth
      4. RuntimeError, wenn nichts Konfiguriertes gefunden wurde

    Returns:
        dict mit keys: provider, model, api_key, base_url
    """
    if role:
        with SessionLocal() as db:
            config = get_role_config(db, role)
            if config:
                # Lokale Role-Werte ohne Key: mit auth.json auffüllen
                if not _is_secure(config.get("api_key", "")) and config.get("provider"):
                    auth_key = _api_key_from_auth(config["provider"])
                    if _is_secure(auth_key):
                        config["api_key"] = auth_key
                        config["base_url"] = config["base_url"] or _base_url_for_provider(
                            config["provider"], ""
                        )
                return config

    # Fallback auf ENV-Variablen + auth.json (Priorität: MiniMax -> Kimi -> OpenAI -> OpenRouter)
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
            "https://api.moonshot.ai/v1",
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
        cfg = _resolve_fallback_config(
            api_key_env, provider, model, base_url_env, default_base_url
        )
        if cfg:
            return cfg

    raise RuntimeError(
        "Keine Provider-Konfiguration für die Rolle und kein API-Key in ENV oder auth.json konfiguriert"
    )


def list_available_env_configs() -> list[dict]:
    """Liefert alle konfigurierten Provider, für die ein API-Key vorhanden ist.

    Reihenfolge entspricht der Fallback-Priorität von resolve_model_config().
    """
    configs: list[dict] = []
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
            "https://api.moonshot.ai/v1",
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
        cfg = _resolve_fallback_config(
            api_key_env, provider, model, base_url_env, default_base_url
        )
        if cfg:
            configs.append(cfg)
    return configs
