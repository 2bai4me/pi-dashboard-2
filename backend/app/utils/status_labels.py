"""Status-Labels Mapping (User-Direktive 18.06.2026).

DB-interner Key (status Spalte in tasks) vs. User-Anzeige-Name.

Mapping:
  DB-Key       -> Display
  'triage'     -> 'Triage'
  'todo'       -> 'GO'         (Phase zwischen Triage und In Progress)
  'in_progress'-> 'In Progress'
  'review'     -> 'Review'
  'block'      -> 'Block' oder 'Rueckfrage' (je nach Kontext)
  'done'       -> 'Done'
  'rueckfrage' -> 'Rueckfrage'
  'warten'     -> 'Warten'

WICHTIG: 'todo' ist der interne DB-Key, der NICHT geaendert werden darf
(sonst bricht alles). Die Anzeige im Frontend und in User-facing Texten
muss aber 'GO' sein.

Diese Utility ist die zentrale Stelle fuer die Umwandlung. Wenn neue
Phasen dazukommen, hier ergaenzen.
"""
from __future__ import annotations

from typing import Optional, Dict, Any


# === DB-Key -> Display-Name ===
DB_TO_DISPLAY: Dict[str, str] = {
    "triage": "Triage",
    "todo": "GO",
    "in_progress": "In Progress",
    "review": "Review",
    "block": "Block",
    "rueckfrage": "Rueckfrage",
    "done": "Done",
    "warten": "Warten",
    "waiting": "Warten",
    "cancelled": "Abgebrochen",
    "failed": "Fehlgeschlagen",
    "completed": "Abgeschlossen",
    "running": "Laeuft",
}


def display_status(db_status: Optional[str]) -> str:
    """Konvertiert einen DB-Status-Key in den User-Anzeige-Namen.

    Args:
        db_status: DB-Key (z.B. 'todo', 'in_progress', 'block')

    Returns:
        Display-Name (z.B. 'GO', 'In Progress', 'Block')

    Beispiele:
        >>> display_status('todo')
        'GO'
        >>> display_status('in_progress')
        'In Progress'
        >>> display_status(None)
        '—'
    """
    if not db_status:
        return "—"
    return DB_TO_DISPLAY.get(db_status.lower(), db_status)


def display_status_with_emoji(db_status: Optional[str]) -> str:
    """Konvertiert DB-Status in Display + Emoji.

    Returns:
        z.B. '🔄 Triage', '✅ GO', '⚙️ In Progress', '🔍 Review', '⛔ Block', '✅ Done'
    """
    EMOJI_MAP = {
        "triage": "🔄",
        "todo": "✅",      # GO Phase
        "in_progress": "⚙️",
        "review": "🔍",
        "block": "⛔",
        "rueckfrage": "❓",
        "done": "✅",
        "warten": "⏸️",
        "waiting": "⏸️",
        "cancelled": "🚫",
        "failed": "❌",
        "completed": "✅",
        "running": "▶️",
    }
    if not db_status:
        return "—"
    emoji = EMOJI_MAP.get(db_status.lower(), "")
    display = display_status(db_status)
    return f"{emoji} {display}".strip() if emoji else display


def translate_status_field(field_value: Optional[str]) -> Optional[str]:
    """Fuer Felder wie 'from_status' / 'to_status' in History/Transitions.

    Diese Felder sind IMMER DB-Keys, sollen aber in der Anzeige
    als Display-Name erscheinen. Wenn der Wert 'todo' ist, soll
    'GO' angezeigt werden.
    """
    if field_value is None:
        return None
    return display_status(field_value)


def translate_history_details(details: Any) -> Any:
    """Rekursiv durch ein dict/list gehen und 'todo' (DB-Key) durch 'GO' ersetzen
    in Feldern, die wie Status-Felder aussehen.

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
                if k in STATUS_FIELD_NAMES and isinstance(v, str) and v.lower() in DB_TO_DISPLAY
                else translate_history_details(v)
            )
            for k, v in details.items()
        }
    if isinstance(details, list):
        return [translate_history_details(item) for item in details]
    return details


def translate_task_dict(task_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Konvertiert status-Felder in einem Task-Dict zu Display-Namen.

    Modifiziert das dict IN-PLACE und gibt es zurueck.
    """
    if not isinstance(task_dict, dict):
        return task_dict
    for field in ("status",):
        if field in task_dict and task_dict[field]:
            # Original-Wert behalten in _status_db (fuer API-Consumer)
            if "_status_db" not in task_dict:
                task_dict["_status_db"] = task_dict[field]
            task_dict[f"{field}_display"] = display_status(task_dict[field])
    return task_dict


# === Test-Snippet (nur bei direktem Aufruf) ===
if __name__ == "__main__":
    test_cases = [
        ("todo", "GO"),
        ("in_progress", "In Progress"),
        ("block", "Block"),
        ("rueckfrage", "Rueckfrage"),
        ("done", "Done"),
        (None, "—"),
        ("unknown", "unknown"),
    ]
    print("=== display_status Tests ===")
    for db, expected in test_cases:
        result = display_status(db)
        ok = "OK" if result == expected else "FAIL"
        print(f"  [{ok}] display_status({db!r}) = {result!r} (expected {expected!r})")

    print("\n=== display_status_with_emoji Tests ===")
    for db in ["triage", "todo", "in_progress", "done"]:
        print(f"  display_status_with_emoji({db!r}) = {display_status_with_emoji(db)!r}")

    print("\n=== translate_history_details Tests ===")
    test_details = {
        "from": "todo",
        "to": "in_progress",
        "reason": "sop_rule:9d0651b20513",
        "auto_mode": True,
        "from_status": "triage",
        "to_status": "todo",
        "old_status": "todo",
        "new_status": "in_progress",
        "description": "Test description with todo word (should NOT be replaced)",
    }
    print(f"  Vorher: {test_details}")
    print(f"  Nachher: {translate_history_details(test_details)}")
