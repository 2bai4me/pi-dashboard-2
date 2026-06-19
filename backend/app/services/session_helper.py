"""Session-Helper: Generiert und persistiert Session-IDs.

Eine Session-ID identifiziert, welche Konversation / welcher Agent
einen Task bearbeitet hat. Wird in task_transitions und task_history
gespeichert.

Format: "session-{type}-{12hex}"
- "user-{12hex}" - User-Aktion (Frontend, Drag&Drop, etc.)
- "worker-{12hex}" - Worker-Loop (auto)
- "triage-{12hex}" - Auto-Triage-Operator
- "sop-{12hex}" - SOP-Engine

Die Session-ID wird im DB-File (oder in env) gespeichert, damit sie
ueber mehrere Requests konsistent bleibt.
"""
import os
import uuid
import logging
import threading

logger = logging.getLogger("pi-dashboard-2.session")

_lock = threading.Lock()
_session_id: str = ""


def _detect_type() -> str:
    """Erkennt den aktuellen Prozess-Typ."""
    if os.getenv("WORKER_LOOP_TYPE"):
        return os.getenv("WORKER_LOOP_TYPE")
    if os.getenv("AUTO_TRIAGE_TYPE"):
        return os.getenv("AUTO_TRIAGE_TYPE")
    # Heuristik: Wenn der Server-Name 'uvicorn' ist und kein Worker-Loop,
    # dann ist es ein API-Request
    return "user"


def init_session_id(force_type: str = None) -> str:
    """Initialisiert die Session-ID (einmalig pro Prozess).

    Sollte einmal beim App-Startup aufgerufen werden, um eine stabile
    Session-ID fuer den Prozess zu haben.
    """
    global _session_id
    with _lock:
        if not _session_id:
            prefix = force_type or _detect_type()
            short = uuid.uuid4().hex[:12]
            _session_id = f"session-{prefix}-{short}"
            logger.info(f"Session-ID initialisiert: {_session_id}")
        return _session_id


def get_session_id() -> str:
    """Gibt die aktuelle Session-ID zurueck (initialisiert bei Bedarf)."""
    if not _session_id:
        init_session_id()
    return _session_id


def get_or_create_session_id() -> str:
    """Alias fuer get_session_id()."""
    return get_session_id()


def set_session_id(session_id: str) -> None:
    """Setzt die Session-ID manuell (z.B. fuer Tests)."""
    global _session_id
    with _lock:
        _session_id = session_id
