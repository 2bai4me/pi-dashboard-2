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
from .role_service import RoleService

logger = logging.getLogger("pi-dashboard-2.subagent")


# Fallback-Werte, falls eine Rolle in der DB unvollstaendig ist.
_FALLBACK_MODEL = "minimax-m3"
_FALLBACK_PROVIDER = "minimax-direct"
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
        """Listet alle verfuegbaren Sub-Agent-Konfigurationen aus der DB.

        Stellt sicher, dass alle Default-Rollen (pi-coder, pi-tester,
        pi-reviewer, pi-fixer + Org-Rollen) vorhanden sind, bevor die
        Konfigurationen zurueckgegeben werden. So kann eine versehentlich
        geloeschte Standard-Rolle nicht stillschweigend fehlen — beim
        naechsten GET kommt sie automatisch zurueck (idempotente Recovery).

        Der Fix ist hier bewusst, weil die SubAgent-UI genau diesen
        Endpoint aufruft. /api/roles/sub-agents macht es bereits analog.
        """
        # Idempotente Recovery: fehlende Standard-Rollen wiederherstellen
        RoleService.seed_defaults(db)

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
                "display_name": role.display_name,
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
                "assigned_sop_id": role.assigned_sop_id,
                "user_modified": role.user_modified,  # User-Direktive 24.06.2026
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
            model: z.B. "minimax-m3" (Standard, User-Direktive 24.06.2026) oder "ollama/gemma4:12b"
            provider: z.B. "minimax-direct" (Standard) oder "ollama" (auto-erkannt wenn None)
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

        # User-Direktive 24.06.2026: Override-Schutz aktivieren
        # Damit seed_defaults() beim Restart die Aenderung NICHT ueberschreibt.
        role.user_modified = True

        db.commit()
        db.refresh(role)
        logger.info(
            f"Role {role_name}: model={role.model}, provider={role.provider}, "
            f"api_key_id={role.api_key_id}, user_modified=True"
        )
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
        # User-Direktive 24.06.2026: Override-Schutz
        role.user_modified = True
        db.commit()
        db.refresh(role)
        logger.info(
            f"Role {role_name}: system_prompt updated ({len(system_prompt)} chars), user_modified=True"
        )
        return role

    @staticmethod
    def update_role_name(
        db: Session,
        role_name: str,
        display_name: Optional[str],
    ) -> Role:
        """Aktualisiert den editierbaren Anzeigenamen einer Rolle.

        `name` (der technische Rollen-Identifier) bleibt unveraendert,
        damit bestehende Lookups und SOP-Referenzen stabil bleiben.
        Nur `display_name` wird gespeichert (kann auch auf None/leer
        zurueckgesetzt werden, dann faellt die Anzeige auf `name`
        zurueck).

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"
            display_name: Neuer Anzeigename oder leerer String fuer Reset

        Returns:
            Aktualisierte Role
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")

        cleaned = (display_name or "").strip()
        role.display_name = cleaned if cleaned else None
        db.commit()
        db.refresh(role)
        logger.info(f"Role {role_name}: display_name={role.display_name!r}")
        return role

    @staticmethod
    def update_role_sop(
        db: Session,
        role_name: str,
        sop_id: Optional[str],
    ) -> Role:
        """Ordnet einer Rolle einen SOP zu (rein informativ).

        Beeinflusst die Prozesssteuerung NICHT – der SOP kann hier nur als
        Dokumentation hinterlegt werden, mit welcher Standard-Operating-
        Procedure der Sub-Agent arbeitet.

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"
            sop_id: SOP-ID (z.B. aus /api/sops) oder None zum Loeschen

        Returns:
            Aktualisierte Role
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")

        cleaned = (sop_id or "").strip() or None
        if cleaned:
            # Pruefen ob der SOP existiert (nur informativ)
            from ..models.sop import SOP
            exists = db.execute(select(SOP).where(SOP.id == cleaned)).scalar_one_or_none()
            if not exists:
                raise ValueError(f"SOP '{cleaned}' nicht gefunden.")
        role.assigned_sop_id = cleaned
        # User-Direktive 24.06.2026: Override-Schutz
        role.user_modified = True
        db.commit()
        db.refresh(role)
        logger.info(
            f"Role {role_name}: assigned_sop_id={role.assigned_sop_id!r}, user_modified=True"
        )
        return role

    @staticmethod
    def update_role_config(
        db: Session,
        role_name: str,
        display_name: Optional[str] = None,
        sop_id: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        api_key_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Role:
        """Aktualisiert mehrere Felder einer Rolle in einem atomaren Aufruf.

        Felder die hier nicht explizit uebergeben werden, bleiben unveraendert.
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")

        from ..models.sop import SOP

        if display_name is not None:
            cleaned = (display_name or "").strip()
            role.display_name = cleaned if cleaned else None

        if sop_id is not None:
            cleaned = (sop_id or "").strip() or None
            if cleaned:
                exists = db.execute(
                    select(SOP).where(SOP.id == cleaned)
                ).scalar_one_or_none()
                if not exists:
                    raise ValueError(f"SOP '{cleaned}' nicht gefunden.")
            role.assigned_sop_id = cleaned

        if api_key_id is not None:
            cleaned = (api_key_id or "").strip() or None
            if cleaned:
                credential = db.get(ProviderCredential, cleaned)
                if not credential:
                    raise ValueError(f"ProviderCredential '{cleaned}' nicht gefunden.")
                role.api_key_id = cleaned
                role.provider = credential.provider
                role.model = credential.model
            else:
                role.api_key_id = None

        # Model/Provider nur setzen, wenn api_key_id nicht explizit gesetzt wurde
        # (sonst wuerden sie durch das Credential ueberschrieben).
        if model is not None and api_key_id is None:
            role.model = (model or "").strip() or None
            if provider is not None:
                role.provider = (provider or "").strip() or None
            elif role.model:
                role.provider = _derive_provider(role.model, role.provider)

        if system_prompt is not None:
            role.system_prompt = system_prompt

        # User-Direktive 24.06.2026: Override-Schutz aktivieren,
        # sobald irgendein protected field geaendert wurde.
        # Vorher wurde user_modified nur in /api/roles/{id} gesetzt — NICHT hier.
        protected_changed = (
            display_name is not None or
            sop_id is not None or
            api_key_id is not None or
            model is not None or
            provider is not None or
            system_prompt is not None
        )
        if protected_changed:
            role.user_modified = True

        db.commit()
        db.refresh(role)
        logger.info(
            f"Role {role_name}: config updated, user_modified={role.user_modified}"
        )
        return role

    @staticmethod
    def delete_role(db: Session, role_name: str) -> Dict[str, Any]:
        """Loescht eine Rolle unwiderruflich aus der DB.

        Andere Tabellen referenzieren Rollen nur als String (z.B.
        task.assigned_role, token_usage.role), nicht per FK – daher
        bleiben historische Eintraege erhalten und zeigen weiterhin den
        Namen an. Nur die Konfiguration (Modell, Provider, Prompt, ...)
        geht verloren.

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"

        Returns:
            Dict mit geloeschter Rolle

        Raises:
            ValueError: Wenn die Rolle nicht gefunden wurde
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")

        snapshot = role.to_dict() if hasattr(role, "to_dict") else {"name": role.name}
        db.delete(role)
        db.commit()
        logger.info(f"Role {role_name} geloescht (Historische Referenzen bleiben erhalten)")
        return snapshot
