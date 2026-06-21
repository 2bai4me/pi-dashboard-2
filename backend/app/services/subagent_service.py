"""SubAgent Service - Baut Sub-Agenten mit konfiguriertem Modell auf.

User-Direktive 18.06.2026: Beim Aufbau eines Sub-Agenten MUSS das in der
Role konfigurierte Modell geladen werden.

User-Direktive 20.06.2026: Jede Rolle hat eine editierbare Beschreibung
(system_prompt) und kann direkt einen API-Key/Provider referenzieren.

Architektur:
  1. Rolle aus DB laden (Role-Model) — Role-Service ist die alleinige Quelle.
  2. Modell + Provider + API-Key via ProviderResolver auflösen.
  3. System-Prompt + Tools aus Role extrahieren.
  4. SubAgent-Instanz bauen.
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.role import Role
from ..models.task import Task
from ..models.provider_credential import ProviderCredential
from .provider_resolver import get_role_config
from .llm_service import chat_completion

logger = logging.getLogger("pi-dashboard-2.subagent")


# Fallback-Werte, falls eine Rolle in der DB unvollstaendig ist.
_FALLBACK_MODEL = "ollama/gemma4:12b"
_FALLBACK_PROVIDER = "ollama"
_FALLBACK_TOOLS = ["read", "write", "bash", "grep"]
_FALLBACK_TEMPERATURE = 0.3
_FALLBACK_MAX_TOKENS = 4096
_FALLBACK_TIMEOUT_SEC = 120.0


def _derive_provider(model: Optional[str], fallback: Optional[str]) -> str:
    """Erkennt den Provider anhand des Modell-Namens."""
    if fallback:
        return fallback
    if model and model.startswith("ollama/"):
        return "ollama"
    if model and "minimax" in model.lower():
        return "minimax-direct"
    return _FALLBACK_PROVIDER


@dataclass
class SubAgent:
    """Ein konfigurierter Sub-Agent mit Modell + System-Prompt + Tools."""
    name: str
    model: str
    provider: Optional[str] = None
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    temperature: float = _FALLBACK_TEMPERATURE
    max_tokens: int = _FALLBACK_MAX_TOKENS
    timeout_sec: float = _FALLBACK_TIMEOUT_SEC
    role_id: Optional[str] = None
    task: Optional[Task] = None

    async def run(self, prompt: str, **kwargs) -> str:
        """Fuehrt den Sub-Agent mit dem konfigurierten Modell aus."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        return await chat_completion(
            messages=messages,
            model=self.model,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            timeout_sec=kwargs.get("timeout_sec", self.timeout_sec),
            role=self.name,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "provider": self.provider,
            "tools": self.tools,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "role_id": self.role_id,
            "task_id": self.task.id if self.task else None,
            "system_prompt_preview": self.system_prompt[:200] + "..." if len(self.system_prompt) > 200 else self.system_prompt,
        }


class SubAgentService:
    """Service zum Aufbau von Sub-Agenten mit konfiguriertem Modell."""

    @staticmethod
    def get_role(db: Session, role_name: str) -> Optional[Role]:
        """Laedt die Rolle aus der DB."""
        return db.execute(
            select(Role).where(Role.name == role_name)
        ).scalar_one_or_none()

    @staticmethod
    def build_agent(
        db: Session,
        role_name: str,
        task: Optional[Task] = None,
        override_model: Optional[str] = None,
    ) -> SubAgent:
        """Baut einen Sub-Agent mit dem aus der Role konfigurierten Modell.

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder", "pi-tester", "CIO"
            task: Optional Task (fuer task-spezifischen System-Prompt)
            override_model: Optional Modell-Override (z.B. fuer Tests)

        Returns:
            SubAgent-Instanz mit konfiguriertem Modell

        Raises:
            ValueError: Wenn die Rolle nicht gefunden wurde
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden. Bitte zuerst seed_defaults aufrufen.")

        # Modell/Provider aus Role/Credential auflösen (oder override)
        if override_model:
            model = override_model
            provider = _derive_provider(model, None)
        else:
            config = get_role_config(db, role_name)
            if config:
                model = config["model"]
                provider = config["provider"]
            else:
                model = role.model or _FALLBACK_MODEL
                provider = role.provider or _derive_provider(model, None)

        # System-Prompt aus Role; task-spezifische Platzhalter werden gefuellt.
        system_prompt_template = role.system_prompt or f"Du bist {role_name}. Bearbeite deine zugewiesenen Tasks."
        try:
            system_prompt = system_prompt_template.format(
                task_title=task.title if task else "(kein Titel)",
                task_id=task.id if task else "(keine ID)",
                task_description=(task.description or "")[:500] if task else "",
            )
        except (KeyError, IndexError):
            # Template enthaelt unbekannte Platzhalter -> unformatiert verwenden
            system_prompt = system_prompt_template

        tools = role.tool_whitelist or _FALLBACK_TOOLS
        timeout_sec = float(role.timeout_sec) if role.timeout_sec else _FALLBACK_TIMEOUT_SEC

        return SubAgent(
            name=role_name,
            model=model,
            provider=provider,
            system_prompt=system_prompt,
            tools=tools,
            timeout_sec=timeout_sec,
            role_id=role.id,
            task=task,
        )

    @staticmethod
    def list_agent_configs(db: Session) -> List[Dict[str, Any]]:
        """Listet alle verfuegbaren Sub-Agent-Konfigurationen aus der DB."""
        result = []
        roles = db.execute(select(Role)).scalars().all()
        for role in roles:
            is_subagent = role.role_type == "sub_agent"

            # Aufgelöste Konfiguration anzeigen
            config = get_role_config(db, role.name)
            if config:
                model = config["model"]
                provider = config["provider"]
            else:
                model = role.model or _FALLBACK_MODEL
                provider = role.provider or _derive_provider(role.model, None)

            result.append({
                "name": role.name,
                "role_id": role.id,
                "role_type": role.role_type,
                "is_subagent": is_subagent,
                "model": model,
                "provider": provider,
                "api_key_id": role.api_key_id,
                "default_model": role.model or _FALLBACK_MODEL,
                "tools": role.tool_whitelist or _FALLBACK_TOOLS,
                "emoji": role.emoji,
                "system_prompt": role.system_prompt,
                "description": role.description,
            })
        return result

    @staticmethod
    def update_role_model(
        db: Session,
        role_name: str,
        model: str,
        provider: Optional[str] = None,
        api_key_id: Optional[str] = None,
    ) -> Role:
        """Aktualisiert das Modell/Provider/API-Key einer Rolle.

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"
            model: z.B. "ollama/gemma4:12b" oder "minimax-m3"
            provider: z.B. "ollama" oder "minimax-direct" (auto-erkannt wenn None)
            api_key_id: Optional ID einer ProviderCredential. Wenn gesetzt,
                        werden provider/model aus der Credential übernommen.

        Returns:
            Aktualisierte Role
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")

        if api_key_id:
            credential = db.get(ProviderCredential, api_key_id)
            if not credential:
                raise ValueError(f"ProviderCredential '{api_key_id}' nicht gefunden.")
            role.api_key_id = api_key_id
            role.provider = credential.provider
            role.model = credential.model
        else:
            role.api_key_id = None
            role.model = model
            role.provider = provider or _derive_provider(model, role.provider)

        db.commit()
        db.refresh(role)
        logger.info(f"Role {role_name}: model={role.model}, provider={role.provider}, api_key_id={role.api_key_id}")
        return role

    @staticmethod
    def update_role_prompt(db: Session, role_name: str, system_prompt: str) -> Role:
        """Aktualisiert den System-Prompt / die Rollenbeschreibung einer Rolle.

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"
            system_prompt: Neuer System-Prompt-Text

        Returns:
            Aktualisierte Role
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")
        role.system_prompt = system_prompt
        db.commit()
        db.refresh(role)
        logger.info(f"Role {role_name}: system_prompt updated ({len(system_prompt)} chars)")
        return role
