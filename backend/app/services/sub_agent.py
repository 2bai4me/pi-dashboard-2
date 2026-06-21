"""Sub-Agent-Spawner (Wrapper) — Nutzt den neuen Sub-Agent-Service aus services/micro/.

Dieser Wrapper stellt die alte sub_agent.py-Schnittstelle bereit,
damit bestehende Router ohne Änderungen funktionieren.
Die eigentliche Logik (RCE-gehärtet) liegt im Sub-Agent-Service.

Migration: Ersetze in Routern:
  from ..services.sub_agent import spawn_sub_agent
  → from ..services.micro.sub_agent_service import spawn_sub_agent

Wichtige Änderungen (v2.0-rc):
  - SPAWN_SH_PATH muss in .env gesetzt sein (kein hartcodierter Pfad mehr)
  - Input-Validierung via Positiv-Liste (keine Shell-Metazeichen erlaubt)
  - Budget-Guard: max. 3 Sub-Agents pro Task
  - Timeout: 30 Minuten
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models.task import Task
from .micro.sub_agent_service import (
    spawn_sub_agent as _spawn_sub_agent,
    kill_sub_agent as _kill_sub_agent,
    get_agent_for_task as _get_agent_for_task,
    list_active_agents as _list_active_agents,
    cleanup_dead_agents as _cleanup_dead_agents,
)


async def spawn_sub_agent(
    t: Task,
    db: Session,
    user: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Startet einen Sub-Agent für einen Task.
    
    Delegiert an den RCE-gehärteten Sub-Agent-Service.
    
    Args:
        t: Task (muss assigned_subagent oder assigned_role haben)
        db: SQLAlchemy-Session
        user: Optionaler User für Audit-Log
    
    Returns:
        Dict mit pid, spawned_at, log_path, role oder None bei Fehler
    
    Raises:
        InvalidInputError: Bei ungültigen Eingaben (RCE-Prävention)
        SubAgentError: Bei fehlendem spawn.sh oder bash
    """
    return await _spawn_sub_agent(t, db, user)


def kill_sub_agent(task_id: str) -> bool:
    """Beendet einen Sub-Agent-Prozess."""
    return _kill_sub_agent(task_id)


def get_agent_for_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Gibt Agent-Info für einen Task zurück."""
    return _get_agent_for_task(task_id)


def list_active_agents() -> list:
    """Listet alle aktiven Sub-Agent-Prozesse."""
    return _list_active_agents()


def cleanup_dead_agents() -> int:
    """Entfernt abgestürzte Agenten aus der Registry."""
    return _cleanup_dead_agents()
