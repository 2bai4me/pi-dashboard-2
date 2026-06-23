"""Task-Decomposer: Erkennt ob ein Task in mehrere zerlegt werden sollte.

User-Direktive 23.06.2026 (Task 4bf7146b0780):
- Wenn User-Anforderung thematisch unterschiedlich: zerlegen
- Wenn ein Thema: als ein Task belassen
- Heuristik: Themen-Marker erkennen (Frontend, Backend, Tests, API, DB, etc.)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("pi-dashboard-2.task_decomposer")


# === Themen-Marker (kann erweitert werden) ===

THEME_KEYWORDS = {
    "frontend": ["frontend", "ui", "react", "vue", "angular", "css", "html", "ux", "design"],
    "backend": ["backend", "api", "server", "endpoint", "route", "fastapi", "flask"],
    "database": ["datenbank", "database", "db", "sql", "migration", "schema", "model"],
    "tests": ["test", "tests", "testing", "pytest", "vitest", "unittest"],
    "deployment": ["deploy", "deployment", "docker", "ci/cd", "build", "release"],
    "documentation": ["dokumentation", "docs", "readme", "documentation", "doc"],
    "security": ["security", "auth", "jwt", "oauth", "berechtigung", "permission"],
    "performance": ["performance", "optimierung", "optimization", "cache", "speed"],
    "monitoring": ["monitoring", "logging", "telemetry", "metric", "observability"],
    "infrastructure": ["infra", "infrastructure", "server", "cloud", "kubernetes"],
}


@dataclass
class DecompositionResult:
    should_split: bool
    detected_themes: List[str]
    proposed_subtasks: List[dict]
    rationale: str


def detect_themes(text: str) -> List[str]:
    """Erkennt Themen in einem Text anhand von Schluesselwoertern."""
    text_lower = text.lower()
    detected = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                detected.append(theme)
                break
    return detected


def should_decompose(title: str, description: str,
                    min_themes: int = 2,
                    min_description_length: int = 100) -> DecompositionResult:
    """Entscheidet ob ein Task zerlegt werden sollte.

    Heuristik:
    - Mindestens 2 verschiedene Themen erkannt
    - Description lang genug (> min_description_length Zeichen)
    - Mehrere Saetze oder Aufzaehlungen erkennbar

    Args:
        title: Task-Titel
        description: Task-Description
        min_themes: Mindest-Anzahl Themen fuer Split
        min_description_length: Mindest-Laenge der Description

    Returns:
        DecompositionResult mit should_split, detected_themes, proposed_subtasks, rationale
    """
    full_text = f"{title}\n{description}"
    detected = detect_themes(full_text)

    # Mehrere Saetze?
    sentence_count = len(re.split(r'[.!?]\s+', description.strip()))

    # Aufzaehlungen? (z.B. "- ", "* ", "1.")
    has_list = bool(re.search(r'^\s*[-*]\s', description, re.MULTILINE)) or bool(re.search(r'^\s*\d+\.\s', description, re.MULTILINE))

    should_split = (
        len(detected) >= min_themes
        and len(description) >= min_description_length
        and (sentence_count >= 2 or has_list)
    )

    if not should_split:
        return DecompositionResult(
            should_split=False,
            detected_themes=detected,
            proposed_subtasks=[],
            rationale=f"Nur {len(detected)} Thema(s) erkannt oder Description zu kurz - kein Split noetig.",
        )

    # Erstelle Sub-Task-Vorschlaege (einer pro Thema + ggf. ein uebergreifender Setup-Task)
    proposed = []
    for theme in detected:
        proposed.append({
            "title": f"{title} - {theme.capitalize()}-Teil",
            "description": (
                f"Sub-Task fuer den Aspekt '{theme}' des Hauptauftrags.\n\n"
                f"Original-Beschreibung:\n{description}\n\n"
                f"Fokus: nur den '{theme}'-Teil umsetzen."
            ),
            "theme": theme,
            "priority": 50,
        })

    return DecompositionResult(
        should_split=True,
        detected_themes=detected,
        proposed_subtasks=proposed,
        rationale=(
            f"{len(detected)} verschiedene Themen erkannt: {', '.join(detected)}. "
            f"Split in {len(proposed)} Sub-Tasks empfohlen."
        ),
    )


def create_subtasks_from_decomposition(
    parent_task_id: str,
    decomposition: DecompositionResult,
    project_id: Optional[str] = None,
    db=None,
) -> List[dict]:
    """Erstellt die vorgeschlagenen Sub-Tasks in der DB.

    Returns:
        Liste der erstellten Sub-Task-IDs
    """
    import secrets
    import sqlite3
    import os
    import json
    from datetime import datetime, timezone

    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Parent-Task lesen fuer project_id
    if project_id is None:
        cur.execute("SELECT project_id FROM tasks WHERE id = ?", (parent_task_id,))
        row = cur.fetchone()
        if row:
            project_id = row["project_id"]

    created_ids = []
    now = datetime.now(timezone.utc).isoformat()
    for st in decomposition.proposed_subtasks:
        subtask_id = secrets.token_hex(6)
        cur.execute("""INSERT INTO tasks
                       (id, project_id, parent_id, title, description, status,
                        priority, category, iteration_count, "order", emergency,
                        worker_understanding_confirmed, review_iteration_count,
                        bza_iteration_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (subtask_id, project_id, parent_task_id,
                     st["title"], st["description"], "triage",
                     st.get("priority", 50), "new_request",
                     0, 0, 0, 0, 0, 0))
        # History-Eintrag mit Rationale
        cur.execute("""INSERT INTO task_history
                       (task_id, event, agent, details)
                       VALUES (?, ?, ?, ?)""",
                    (subtask_id, "subtask_created_from_decomposition",
                     "CIO",
                     json.dumps({
                         "parent_task_id": parent_task_id,
                         "theme": st.get("theme"),
                         "rationale": decomposition.rationale,
                     })))
        created_ids.append(subtask_id)

    conn.commit()
    conn.close()
    logger.info(f"{len(created_ids)} Sub-Tasks aus Decomposition erstellt (Parent: {parent_task_id})")
    return created_ids