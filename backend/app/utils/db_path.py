"""DB-Pfad-Resolution (CLEANUP-AUDIT 23.06.2026).

Zentrale Helper-Funktion, damit alle Router/Services den absoluten DB-Pfad nutzen
(auch wenn der Prozess aus wechselndem CWD gestartet wird).

WICHTIG: DB liegt in PROJECT_ROOT/database, NICHT BACKEND_ROOT/database!
BACKEND_ROOT = backend/ , PROJECT_ROOT = backend/../
"""
from __future__ import annotations

import os
from functools import lru_cache

from ..config import PROJECT_ROOT


@lru_cache(maxsize=1)
def get_default_db_path() -> str:
    """Liefert den absoluten Pfad zur Default-SQLite-DB (database/pi_dashboard.db).

    Wird per lru_cache gecached, damit nicht bei jedem Request neu berechnet.
    """
    return os.path.join(str(PROJECT_ROOT), "database", "pi_dashboard.db")


def resolve_db_path() -> str:
    """Liefert den aktiven DB-Pfad (ENV PI_DB_PATH oder Default)."""
    return os.environ.get("PI_DB_PATH", get_default_db_path())


__all__ = ["get_default_db_path", "resolve_db_path"]
