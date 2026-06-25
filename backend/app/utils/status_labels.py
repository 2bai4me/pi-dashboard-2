"""Status-Labels Mapping (User-Direktive 18.06.2026).

DB-interner Key (status Spalte in tasks) vs. User-Anzeige-Name + Emoji.

Mapping:
  DB-Key       -> Display
  'triage'     -> 'Triage'
  'todo'       -> 'GO'         (Phase zwischen Triage und In Progress)
  'in_progress'-> 'In Progress'
  'review'     -> 'Review'
  'block'      -> 'Block'
  'done'       -> 'Done'
  'rueckfrage' -> 'Rueckfrage'
  'warten'     -> 'Warten'

WICHTIG: 'todo' ist der interne DB-Key, der NICHT geaendert werden darf.
"""
from __future__ import annotations

from typing import Optional, Dict, Any


# === DB-Key -> {display, emoji} ===
_STATUS_MAP: Dict[str, Dict[str, str]] = {
    "triage": {"display": "Triage", "emoji": "🔄"},
    "todo": {"display": "GO", "emoji": "✅"},
    "in_progress": {"display": "In Progress", "emoji": "⚙️"},
    "review": {"display": "Review", "emoji": "🔍"},
    "block": {"display": "Block", "emoji": "⛔"},
    "rueckfrage": {"display": "Rueckfrage", "emoji": "❓"},
    "done": {"display": "Done", "emoji": "✅"},
    "warten": {"display": "Warten", "emoji": "⏸️"},
    "waiting": {"display": "Warten", "emoji": "⏸️"},
    "cancelled": {"display": "Abgebrochen", "emoji": "🚫"},
    "failed": {"display": "Fehlgeschlagen", "emoji": "❌"},
    "completed": {"display": "Abgeschlossen", "emoji": "✅"},
    "running": {"display": "Laeuft", "emoji": "▶️"},
}


def display_status(db_status: Optional[str]) -> str:
    """Konvertiert einen DB-Status-Key in den User-Anzeige-Namen."""
    if not db_status:
        return "—"
    return _STATUS_MAP.get(db_status.lower(), {}).get("display", db_status)


def display_status_with_emoji(db_status: Optional[str]) -> str:
    """Konvertiert DB-Status in Display + Emoji."""
    if not db_status:
        return "—"
    key = db_status.lower()
    info = _STATUS_MAP.get(key, {})
    emoji = info.get("emoji", "")
    display = info.get("display", db_status)
    return f"{emoji} {display}".strip() if emoji else display


def translate_status_field(field_value: Optional[str]) -> Optional[str]:
    """Fuer Felder wie 'from_status' / 'to_status' in History/Transitions."""
    if field_value is None:
        return None
    return display_status(field_value)


def translate_history_details(details: Any) -> Any:
    """Rekursiv durch ein dict/list gehen und Status-Felder uebersetzen.

    Erkennt Status-Felder anhand der Namen: 'from', 'to', 'from_status', 'to_status',
    'old_status', 'new_status', 'status'.
    """
    STATUS_FIELD_NAMES = {
        "from", "to", "from_status", "to_status",
        "old_status", "new_status", "status",
    }
    if isinstance(details, dict):
        return {
            k: (
                display_status(v)
                if k in STATUS_FIELD_NAMES and isinstance(v, str) and v.lower() in _STATUS_MAP
                else translate_history_details(v)
            )
            for k, v in details.items()
        }
    if isinstance(details, list):
        return [translate_history_details(item) for item in details]
    return details


def translate_task_dict(task_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Konvertiert status-Felder in einem Task-Dict zu Display-Namen."""
    if not isinstance(task_dict, dict):
        return task_dict
    for field in ("status",):
        if field in task_dict and task_dict[field]:
            if "_status_db" not in task_dict:
                task_dict["_status_db"] = task_dict[field]
            task_dict[f"{field}_display"] = display_status(task_dict[field])
    return task_dict
