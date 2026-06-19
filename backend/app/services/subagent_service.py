"""SubAgent Service - Baut Sub-Agenten mit konfiguriertem Modell auf.

User-Direktive 18.06.2026: Beim Aufbau eines Sub-Agenten MUSS das in der
Role konfigurierte Modell geladen werden. Standard fuer Sub-Agenten
(pi-coder, pi-tester, pi-reviewer, pi-fixer): ollama/gemma4:12b.

Architektur:
  1. Rolle aus DB laden (Role-Model)
  2. Modell + Provider aus Role extrahieren
  3. SubAgent-Instanz bauen mit:
     - model (z.B. ollama/gemma4:12b)
     - system_prompt (rollenspezifisch)
     - tools (z.B. bash, read, write, grep)
     - timeout, temperature, max_tokens
  4. SubAgent ist "ready" fuer den Aufruf via LLM-Service

Verwendung:
  agent = SubAgentService.build_agent("pi-coder", task=task_obj)
  response = await agent.run(prompt="...")
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.role import Role
from ..models.task import Task
from .llm_service import chat_completion, _load_api_credentials

logger = logging.getLogger("pi-dashboard-2.subagent")


# === Default-Konfiguration pro Sub-Agent-Typ ===
# (User-Direktive 18.06.2026: Standard ist ollama/gemma4:12b)
DEFAULT_SUBAGENT_CONFIG = {
    "pi-coder": {
        "model": "ollama/gemma4:12b",
        "provider": "ollama",
        "system_prompt_template": (
            "Du bist pi-coder, ein erfahrener Software-Entwickler. "
            "Deine Aufgabe ist es, den Task '{task_title}' umzusetzen. "
            "Verwende Write/Read/Bash/Grep-Tools. "
            "Liefere am Ende Code, Tests und Commit. "
            "Halte dich an die in der Description dokumentierten Erfolgskriterien. "
            "Dokumentiere alle Aenderungen in task.meta (z.B. test_coverage, criteria_met, criteria_total)."
        ),
        "temperature": 0.3,
        "max_tokens": 4096,
        "tools": ["read", "write", "bash", "grep"],
    },
    "pi-tester": {
        "model": "ollama/gemma4:12b",
        "provider": "ollama",
        "system_prompt_template": (
            "Du bist pi-tester, ein erfahrener QA-Engineer. "
            "Deine Aufgabe ist es, die Implementation des Tasks '{task_title}' zu testen. "
            "Pruefe ALLE in der Description dokumentierten success_criteria. "
            "Fuehre Tests aus, pruefe Coverage, Lint, kritische Issues. "
            "Dokumentiere in task.meta: test_coverage, lint_errors, test_files, critical_issues. "
            "Schreibe am Ende criteria_met/criteria_total in task.meta (vom Worker implementiert)."
        ),
        "temperature": 0.2,
        "max_tokens": 4096,
        "tools": ["read", "bash", "grep"],
    },
    "pi-reviewer": {
        "model": "ollama/gemma4:12b",
        "provider": "ollama",
        "system_prompt_template": (
            "Du bist pi-reviewer, ein erfahrener Code-Reviewer. "
            "Pruefe Code-Qualitaet, Architektur, Best-Practices. "
            "Verwende Read/Grep-Tools, analysiere den Code. "
            "Dokumentiere Findings in task.meta.code_review_findings."
        ),
        "temperature": 0.2,
        "max_tokens": 4096,
        "tools": ["read", "grep"],
    },
    "pi-fixer": {
        "model": "ollama/gemma4:12b",
        "provider": "ollama",
        "system_prompt_template": (
            "Du bist pi-fixer, ein Bug-Fixer. "
            "Analysiere den Bug, fixe ihn, schreibe Tests, commit. "
            "Verwende Read/Write/Bash/Grep. "
            "Dokumentiere Fix-Commits in task.meta.fix_commits."
        ),
        "temperature": 0.2,
        "max_tokens": 4096,
        "tools": ["read", "write", "bash", "grep"],
    },
}

# === C-Level Rollen (nicht Sub-Agenten) ===
C_LEVEL_CONFIG = {
    "CIO": {
        "model": "gemma4:12b",
        "system_prompt_template": (
            "Du bist der CIO. Pruefe Tasks auf Vollstaendigkeit, Klarheit, Konflikte. "
            "Stelle success_criteria fest. Lege Rollenzuweisungen fest."
        ),
    },
    "CEO-digital": {
        "model": "minimax-m3",
        "system_prompt_template": "Du bist CEO-digital. Triff strategische Entscheidungen.",
    },
}


@dataclass
class SubAgent:
    """Ein konfigurierter Sub-Agent mit Modell + System-Prompt + Tools."""
    name: str
    model: str
    provider: Optional[str] = None
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_sec: float = 120.0
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

        # Modell aus Role (oder override)
        if override_model:
            model = override_model
            provider = None
        else:
            model = role.model or DEFAULT_SUBAGENT_CONFIG.get(role_name, {}).get("model", "ollama/gemma4:12b")
            provider = role.provider or DEFAULT_SUBAGENT_CONFIG.get(role_name, {}).get("provider", "ollama")

        # Defaults aus dem Config-Mapping
        default_config = DEFAULT_SUBAGENT_CONFIG.get(role_name, C_LEVEL_CONFIG.get(role_name, {}))
        system_prompt_template = default_config.get(
            "system_prompt_template",
            f"Du bist {role_name}. Bearbeite deine zugewiesenen Tasks."
        )
        tools = default_config.get("tools", ["read", "write", "bash", "grep"])
        temperature = default_config.get("temperature", 0.3)
        max_tokens = default_config.get("max_tokens", 4096)

        # System-Prompt mit Task-Daten fuellen (falls Task gegeben)
        system_prompt = system_prompt_template
        if task:
            system_prompt = system_prompt_template.format(
                task_title=task.title or "(kein Titel)",
                task_id=task.id,
                task_description=(task.description or "")[:500],
            )

        return SubAgent(
            name=role_name,
            model=model,
            provider=provider,
            system_prompt=system_prompt,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            role_id=role.id,
            task=task,
        )

    @staticmethod
    def list_agent_configs(db: Session) -> List[Dict[str, Any]]:
        """Listet alle verfuegbaren Sub-Agent-Konfigurationen."""
        result = []
        roles = db.execute(select(Role)).scalars().all()
        for role in roles:
            is_subagent = role.name in DEFAULT_SUBAGENT_CONFIG
            result.append({
                "name": role.name,
                "role_id": role.id,
                "role_type": role.role_type,
                "is_subagent": is_subagent,
                "model": role.model or DEFAULT_SUBAGENT_CONFIG.get(role.name, {}).get("model"),
                "provider": role.provider or DEFAULT_SUBAGENT_CONFIG.get(role.name, {}).get("provider"),
                "default_model": DEFAULT_SUBAGENT_CONFIG.get(role.name, {}).get("model"),
                "tools": DEFAULT_SUBAGENT_CONFIG.get(role.name, {}).get("tools", []),
                "emoji": role.emoji,
            })
        return result

    @staticmethod
    def update_role_model(db: Session, role_name: str, model: str, provider: Optional[str] = None) -> Role:
        """Aktualisiert das Modell einer Rolle (User-Direktive 18.06.2026: konfigurierbar).

        Args:
            db: SQLAlchemy Session
            role_name: z.B. "pi-coder"
            model: z.B. "ollama/gemma4:12b" oder "minimax-m3"
            provider: z.B. "ollama" oder "minimax-direct" (auto-erkannt wenn None)

        Returns:
            Aktualisierte Role
        """
        role = SubAgentService.get_role(db, role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' nicht in DB gefunden.")
        role.model = model
        # Provider automatisch erkennen wenn nicht angegeben
        if provider:
            role.provider = provider
        elif model.startswith("ollama/"):
            role.provider = "ollama"
        elif "minimax" in model.lower():
            role.provider = "minimax-direct"
        else:
            role.provider = role.provider or "unknown"
        db.commit()
        db.refresh(role)
        logger.info(f"Role {role_name}: model={role.model}, provider={role.provider}")
        return role
