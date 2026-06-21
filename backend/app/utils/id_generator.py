"""Zentrale ID-Generierung für das gesamte Projekt.

Statt `secrets.token_hex(6)` in 12 verschiedenen Dateien zu wiederholen,
nutzen alle Services und Models diese zentrale Funktion.

Formate:
  - `gen_id()`         → 12 Zeichen Hex (Standard, 6 Bytes Entropie)
  - `gen_uuid()`       → 36 Zeichen UUIDv4 (für sicherheitskritische IDs)
  - `gen_short_id()`   → 8 Zeichen (für temporäre/schnelle IDs)
  - `gen_prefixed()`   → z.B. "task-a1b2c3d4e5f6" (für bessere Lesbarkeit)

Migration von `secrets.token_hex(6)` auf `gen_id()`:
  Ersetze in allen Dateien:
    `import secrets` + `def _gen_id(): return secrets.token_hex(6)`
  durch:
    `from ..utils.id_generator import gen_id`
"""
from __future__ import annotations

import secrets
import uuid
from typing import Optional


def gen_id(bytes: int = 6) -> str:
    """Erzeugt eine kryptografisch sichere Hex-ID.
    
    Args:
        bytes: Anzahl der Zufalls-Bytes (Default 6 = 12 Hex-Zeichen)
    
    Returns:
        ID-String (z.B. "a1b2c3d4e5f6")
    
    Beispiel:
        >>> gen_id()
        'a1b2c3d4e5f6'
        >>> gen_id(4)
        'a1b2c3d4'
    """
    return secrets.token_hex(bytes)


def gen_uuid() -> str:
    """Erzeugt eine UUIDv4 (RFC 4122).
    
    Verwendung für sicherheitskritische IDs oder wenn 
    globale Eindeutigkeit garantiert sein muss.
    
    Returns:
        UUID-String (z.B. "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def gen_short_id() -> str:
    """Erzeugt eine kurze ID (8 Zeichen) für temporäre Zwecke.
    
    Returns:
        Kurzer ID-String (z.B. "a1b2c3d4")
    """
    return secrets.token_hex(4)


def gen_prefixed(prefix: str, bytes: int = 6) -> str:
    """Erzeugt eine ID mit lesbarem Prefix.
    
    Args:
        prefix: Text-Prefix (z.B. "task", "project", "sop")
        bytes: Anzahl der Zufalls-Bytes
    
    Returns:
        Prefix-ID (z.B. "task-a1b2c3d4e5f6")
    
    Beispiel:
        >>> gen_prefixed("task")
        'task-a1b2c3d4e5f6'
    """
    return f"{prefix}-{secrets.token_hex(bytes)}"
