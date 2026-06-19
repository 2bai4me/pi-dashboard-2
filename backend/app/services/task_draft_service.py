"""TaskDraft Service — Iterativer Task-Refinement (User-Direktive 18.06.2026).

Workflow:
  1. User beschreibt Task (kurze Notiz, z.B. "Login mit OAuth")
  2. AI generiert vollstaendigen Task-Entwurf (title, description, success_criteria, ...)
  3. User passt an
  4. AI optimiert auf Basis des User-Feedbacks
  5. ... (mehrfach iterieren)
  6. User klickt "Freigeben" -> Task wird erstellt

AI-Backend:
  - Versuche: SubAgent (default: pi-coder mit gemma4:12b, oder CIO)
  - Fallback: Mock-Generator, der den User-Input intelligent erweitert (z.B.
    "Login mit OAuth" -> title="Login mit OAuth2-Provider",
    description="Implementiere OAuth2-Login mit Google-Provider...",
    success_criteria=["Login funktioniert mit Google", "...")
  - Wenn Ollama down: Fallback automatisch
"""
from __future__ import annotations

import logging
import secrets
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.task_draft import TaskDraft
from ..models.task import Task
from ..models.project import Project
from .subagent_service import SubAgentService
from .task_service import TaskService
from .pricing_service import take_pricing_snapshot

logger = logging.getLogger("pi-dashboard-2.task-draft")


# === Mock-Generator (Fallback wenn LLM nicht verfuegbar) ===

# Standard-Boilerplate, der den User-Input intelligent erweitert
DEFAULT_TITLE_PATTERNS = [
    (r"(?i)implement.*oauth", "Implementiere OAuth2-Login"),
    (r"(?i)implement.*login", "Implementiere Login-Funktion"),
    (r"(?i)fix.*bug|bug.*fix", "Bug-Fix: {topic}"),
    (r"(?i)refactor", "Refactoring: {topic}"),
    (r"(?i)test|tests|tests", "Tests: {topic}"),
    (r"(?i)doc|docs|dokumentation", "Dokumentation: {topic}"),
    (r"(?i)deploy|release|production", "Deployment: {topic}"),
]


def _extract_topic(user_input: str) -> str:
    """Extrahiert das Hauptthema aus dem User-Input (sehr einfach)."""
    cleaned = user_input.strip()
    # Entferne typische Anfaenge
    for prefix in ["bitte ", "kannst du ", "ich brauche ", "mach ", "mache ", "implementiere "]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    # Begrenze auf 60 Zeichen
    if len(cleaned) > 60:
        cleaned = cleaned[:60].rsplit(" ", 1)[0] + "..."
    # Capitalize
    return cleaned[0].upper() + cleaned[1:] if cleaned else "Neuer Task"


def _fallback_generate_draft(user_input: str, current: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mock-AI: Generiert einen vollstaendigen Task-Entwurf aus User-Input.

    Wird verwendet wenn das LLM nicht verfuegbar ist.
    """
    topic = _extract_topic(user_input)

    # Wenn ein current-Entwurf existiert, behalte die Struktur und
    # aktualisiere nur die Description/Sections, die der User geaendert hat
    if current:
        new = dict(current)
    else:
        new = {}

    # Bestimme den Titel (User kann ihn jederzeit aendern)
    if "title" not in new or not new.get("title"):
        new["title"] = topic

    # Bestimme die Description: erweitere User-Input um Kontext
    if "description" not in new or not new.get("description"):
        new["description"] = (
            f"## Ziel\n{user_input.strip()}\n\n"
            f"## Vorgehen\n"
            f"1. Anforderung analysieren\n"
            f"2. Implementation planen (Architektur, API, UI)\n"
            f"3. Code schreiben mit Tests\n"
            f"4. Code-Review durch pi-tester\n"
            f"5. CIO-Final-Review\n\n"
            f"## Kontext\n"
            f"Dieser Task wurde ueber den iterativen KI-Workflow angelegt. "
            f"Der User hat folgende initiale Beschreibung gegeben:\n> {user_input}\n\n"
            f"Bitte passe die Description an und fuege Akzeptanzkriterien hinzu."
        )

    # Default success_criteria: die 2 Standard-Defaults
    if "success_criteria" not in new or not new.get("success_criteria"):
        new["success_criteria"] = [
            "Die in der Description dokumentierte Aenderung wurde umgesetzt und ist funktional",
            "Tester hat den Code als gut und fehlerfrei eingestuft (Code-Review bestanden)",
        ]

    # Default priority
    if "priority" not in new:
        new["priority"] = 50

    # Default category
    if "category" not in new:
        # Heuristik: Bug = bugfix, Sonst = new_request
        lower_input = user_input.lower()
        if "bug" in lower_input or "fix" in lower_input or "fehler" in lower_input:
            new["category"] = "bugfix"
        elif "refactor" in lower_input:
            new["category"] = "change"
        else:
            new["category"] = "new_request"

    # Default assigned_role (kann User aendern)
    if "assigned_role" not in new:
        if "test" in user_input.lower():
            new["assigned_role"] = "pi-tester"
        elif "doc" in user_input.lower():
            new["assigned_role"] = "CEO-digital"
        else:
            new["assigned_role"] = "pi-coder"

    # Default tags
    if "tags" not in new:
        new["tags"] = ["ai-generated"]

    # Acceptance Criteria Erklaerung
    if "acceptance_criteria_explanation" not in new:
        new["acceptance_criteria_explanation"] = (
            "Diese Kriterien werden automatisch ergaenzt. "
            "Du kannst sie im Detail-Panel bearbeiten oder eigene hinzufuegen. "
            "Die 2 Standard-Defaults pruefen: (1) Funktion, (2) Code-Review."
        )

    return new


def _fallback_refine_draft(user_input: str, current: Dict[str, Any]) -> Dict[str, Any]:
    """Mock-AI: Verfeinert den Entwurf basierend auf User-Feedback.

    Sehr einfache Heuristik:
    - Wenn User "title" sagt: aendere Titel
    - Wenn User "description" sagt: erweitere Description
    - Wenn User "criteria" sagt: fuege Kriterien hinzu
    - Sonst: fuege Feedback als Notiz zur Description hinzu
    """
    new = dict(current)
    feedback_lower = user_input.lower()

    # Pattern-Matching fuer konkrete Aenderungen
    title_match = re.search(r"(?:title|titel)\s*[:=]?\s*['\"]?([^'\"]+?)['\"]?\s*$", user_input, re.IGNORECASE)
    if title_match:
        new["title"] = title_match.group(1).strip()

    desc_match = re.search(r"(?:description|beschreibung)\s*[:=]?\s*['\"]?(.+?)['\"]?\s*$", user_input, re.IGNORECASE | re.DOTALL)
    if desc_match:
        new["description"] = desc_match.group(1).strip()

    priority_match = re.search(r"(?:priority|prio|prioriaet)\s*[:=]?\s*(\d+)", user_input, re.IGNORECASE)
    if priority_match:
        new["priority"] = int(priority_match.group(1))

    role_match = re.search(r"(?:role|rolle|assigned_role)\s*[:=]?\s*(\w+)", user_input, re.IGNORECASE)
    if role_match:
        new["assigned_role"] = role_match.group(1)

    # Criteria hinzufuegen
    criteria_match = re.search(r"(?:criteria|kriterien|criterion)\s*[:=]?\s*['\"]?(.+?)['\"]?\s*$", user_input, re.IGNORECASE | re.DOTALL)
    if criteria_match:
        new_criterion = criteria_match.group(1).strip()
        if "success_criteria" not in new:
            new["success_criteria"] = []
        if new_criterion not in new["success_criteria"]:
            new["success_criteria"].append(new_criterion)

    # Generelles Feedback: anhaengen
    if not any([title_match, desc_match, priority_match, role_match, criteria_match]):
        # Feedback als Notiz anhaengen
        feedback_note = f"\n\n## User-Feedback (Iteration {len(new.get('iterations', [])) + 1})\n{user_input.strip()}"
        if "description" in new:
            new["description"] = new["description"] + feedback_note
        else:
            new["description"] = user_input.strip()

    return new


# === Service-Klasse ===

class TaskDraftService:
    """Service fuer den iterativen Task-Refinement-Workflow."""

    @staticmethod
    def _gen_id() -> str:
        return f"draft-{secrets.token_hex(8)}"

    @staticmethod
    def create_draft(db: Session, user_input: str, project_id: Optional[str] = None) -> TaskDraft:
        """Erstellt einen neuen Task-Entwurf (User-Beschreibung -> AI-Entwurf).

        Args:
            db: SQLAlchemy Session
            user_input: User-Beschreibung (z.B. "Login mit OAuth")
            project_id: Optional Project-ID

        Returns:
            TaskDraft-Instanz mit AI-generiertem current-Dict
        """
        # Versuche: KI (SubAgent pi-coder)
        ai_output = None
        try:
            agent = SubAgentService.build_agent(db, "pi-coder")
            prompt = (
                f"Du bist ein erfahrener Task-Refiner. Der User hat folgenden Task-Wunsch:\n\n"
                f"USER-INPUT: {user_input}\n\n"
                f"Erstelle einen vollstaendigen Task-Entwurf mit title, description, success_criteria (3-5 Stueck), "
                f"priority (1-100), category (new_request|change|bugfix|ticket), assigned_role (pi-coder|pi-tester|pi-fixer|pi-reviewer|CIO).\n\n"
                f"Antworte NUR mit JSON:\n"
                f'{{"title": "...", "description": "...", "priority": 50, "category": "new_request", "success_criteria": ["..."], "assigned_role": "pi-coder"}}'
            )
            import asyncio
            response_text = asyncio.run(agent.run(prompt))
            # Parse JSON
            import json
            import re as re2
            json_match = re2.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                ai_output = json.loads(json_match.group(0))
                logger.info(f"KI-Draft-Generator: AI hat Output generiert (len={len(response_text)})")
        except Exception as e:
            logger.warning(f"KI-Draft-Generator fehlgeschlagen: {e}. Fallback auf Mock.")

        # Fallback: Mock-Generator
        if not ai_output:
            ai_output = _fallback_generate_draft(user_input)

        # Default project_id
        if not project_id:
            # Erstes aktives Projekt nehmen
            from ..models.project import Project
            proj = db.execute(select(Project).where(Project.status == "active").limit(1)).scalar_one_or_none()
            project_id = proj.id if proj else None

        # current-Dict aufbauen (mit Defaults + KI-Output)
        current = {
            "title": ai_output.get("title", _extract_topic(user_input)),
            "description": ai_output.get("description", f"Bitte anpassen: {user_input}"),
            "priority": ai_output.get("priority", 50),
            "category": ai_output.get("category", "new_request"),
            "success_criteria": ai_output.get("success_criteria", []),
            "assigned_role": ai_output.get("assigned_role", "pi-coder"),
            "project_id": project_id,
            "tags": ["ai-generated"],
            "acceptance_criteria_explanation": (
                "Diese Kriterien wurden automatisch generiert. "
                "Bitte im Detail-Panel anpassen oder eigene hinzufuegen."
            ),
        }
        # Standard-Erfolgskriterien hinzufuegen, wenn keine da sind
        STANDARD_CRITERIA = [
            "Die in der Description dokumentierte Aenderung wurde umgesetzt und ist funktional",
            "Tester hat den Code als gut und fehlerfrei eingestuft (Code-Review bestanden)",
        ]
        for sc in STANDARD_CRITERIA:
            if sc not in current["success_criteria"]:
                current["success_criteria"].append(sc)

        now = datetime.now(timezone.utc)
        draft = TaskDraft(
            id=TaskDraftService._gen_id(),
            user_input=user_input,
            current=current,
            iterations=[{
                "iteration": 1,
                "user_input": user_input,
                "ai_output": dict(ai_output) if ai_output else {"_note": "Mock-Fallback verwendet"},
                "timestamp": now.isoformat(),
            }],
            status="draft",
            created_at=now,
            updated_at=now,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return draft

    @staticmethod
    def refine_draft(db: Session, draft_id: str, user_feedback: str) -> TaskDraft:
        """Verfeinert den Entwurf basierend auf User-Feedback.

        Args:
            db: SQLAlchemy Session
            draft_id: TaskDraft-ID
            user_feedback: User-Feedback (z.B. "title: Login mit Google-OAuth")

        Returns:
            Aktualisierte TaskDraft
        """
        draft = db.get(TaskDraft, draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} nicht gefunden")
        if draft.status != "draft":
            raise ValueError(f"Draft ist nicht mehr im 'draft'-Status (status={draft.status})")

        # Versuche: KI (SubAgent)
        ai_output = None
        try:
            agent = SubAgentService.build_agent(db, "pi-coder")
            prompt = (
                f"Du bist ein erfahrener Task-Refiner. Der User moechte den folgenden Task-Entwurf anpassen.\n\n"
                f"AKTUELLER ENTWURF:\n{json.dumps(draft.current, indent=2, ensure_ascii=False)}\n\n"
                f"USER-FEEDBACK: {user_feedback}\n\n"
                f"Erstelle einen VERFEINERTEN Task-Entwurf. Aendere nur die Felder, die der User geaendert haben will. "
                f"Antworte NUR mit JSON (gleiche Struktur):\n"
                f'{{"title": "...", "description": "...", "priority": 50, "category": "new_request", "success_criteria": ["..."], "assigned_role": "pi-coder"}}'
            )
            import asyncio
            import json
            response_text = asyncio.run(agent.run(prompt))
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                ai_output = json.loads(json_match.group(0))
        except Exception as e:
            logger.warning(f"KI-Draft-Refiner fehlgeschlagen: {e}. Fallback auf Mock.")

        # Fallback: Mock-Refiner
        if not ai_output:
            ai_output = _fallback_refine_draft(user_feedback, draft.current)

        # current mit neuen Werten aktualisieren
        new_current = dict(draft.current)
        for key in ["title", "description", "priority", "category", "assigned_role"]:
            if key in ai_output and ai_output[key]:
                new_current[key] = ai_output[key]
        if "success_criteria" in ai_output and ai_output["success_criteria"]:
            # Mergen: bestehende + neue (keine Duplikate)
            existing = new_current.get("success_criteria", [])
            for sc in ai_output["success_criteria"]:
                if sc not in existing:
                    existing.append(sc)
            new_current["success_criteria"] = existing

        # Iteration speichern
        now = datetime.now(timezone.utc)
        new_iteration = {
            "iteration": len(draft.iterations) + 1,
            "user_input": user_feedback,
            "ai_output": dict(ai_output) if ai_output else {"_note": "Mock-Fallback verwendet"},
            "timestamp": now.isoformat(),
        }
        new_iterations = list(draft.iterations) + [new_iteration]

        draft.current = new_current
        draft.iterations = new_iterations
        draft.updated_at = now
        db.commit()
        db.refresh(draft)
        return draft

