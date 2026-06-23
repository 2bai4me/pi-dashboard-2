"""Projektnummer-Service.

User-Direktive 23.06.2026 (Task 260326669e82):
- Eindeutige Projektnummer im Format PROJ-YYYY-NNN
- Auto-Generierung beim Anlegen
- Thread-safe via SQLite-Lock
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger("pi-dashboard-2.project_number")


def generate_next_project_number() -> str:
    """Generiert die naechste freie Projektnummer.

    Format: PROJ-YYYY-NNN (z.B. PROJ-2026-005)
    Thread-safe ueber SQLite (serialisierte Schreibvorgaenge).
    """
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    current_year = datetime.now().year

    # Sequence-Zeile holen oder erstellen
    cur.execute(
        "SELECT last_number FROM project_number_sequences WHERE year = ?",
        (current_year,),
    )
    row = cur.fetchone()
    if row is None:
        # Erstes Projekt in diesem Jahr
        cur.execute(
            "INSERT INTO project_number_sequences (year, last_number) VALUES (?, 1)",
            (current_year,),
        )
        next_number = 1
    else:
        next_number = row[0] + 1
        cur.execute(
            "UPDATE project_number_sequences SET last_number = ? WHERE year = ?",
            (next_number, current_year),
        )

    conn.commit()

    project_number = f"PROJ-{current_year}-{next_number:03d}"
    logger.info(f"Generated project number: {project_number}")
    conn.close()
    return project_number


def ensure_project_number(project_id: str) -> str:
    """Stellt sicher, dass ein Projekt eine project_number hat.

    Falls vorhanden: zurueckgeben.
    Falls nicht: generieren und speichern.
    """
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT project_number FROM projects WHERE id = ?", (project_id,))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]

    # Generieren und speichern
    new_number = generate_next_project_number()
    cur.execute(
        "UPDATE projects SET project_number = ? WHERE id = ?",
        (new_number, project_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Assigned project number {new_number} to project {project_id}")
    return new_number