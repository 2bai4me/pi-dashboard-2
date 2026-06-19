"""SubAgent Router - Konfiguration und Aufbau von Sub-Agenten.

User-Direktive 18.06.2026: Sub-Agenten sollen konfigurierbar sein mit Modell
pro Rolle. Standard ist ollama/gemma4:12b.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..services.subagent_service import SubAgentService, SubAgent

logger = logging.getLogger("pi-dashboard-2.subagent-router")
router = APIRouter(prefix="/api/subagents", tags=["subagents"])


# === Pydantic-Schemas ===

class AgentConfigRead(BaseModel):
    name: str
    role_id: str
    role_type: Optional[str] = None
    is_subagent: bool
    model: Optional[str] = None
    provider: Optional[str] = None
    default_model: Optional[str] = None
    tools: List[str] = []
    emoji: Optional[str] = None


class AgentRead(BaseModel):
    name: str
    model: str
    provider: Optional[str] = None
    tools: List[str] = []
    temperature: float
    max_tokens: int
    role_id: Optional[str] = None
    task_id: Optional[str] = None
    system_prompt_preview: str


class ModelUpdate(BaseModel):
    model: str
    provider: Optional[str] = None


# === Endpoints ===

@router.get("/configs", response_model=List[AgentConfigRead])
async def list_agent_configs(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle verfuegbaren Sub-Agent-Konfigurationen.

    Zeigt pro Rolle: aktuelles Modell, Provider, Standard-Modell, Tools.
    """
    configs = SubAgentService.list_agent_configs(db)
    return configs


@router.post("/build", response_model=AgentRead)
async def build_agent(
    role_name: str = Query(..., description="z.B. pi-coder, pi-tester, CIO"),
    task_id: Optional[str] = Query(None, description="Optional Task-ID fuer task-spezifischen System-Prompt"),
    override_model: Optional[str] = Query(None, description="Modell-Override fuer Tests"),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Baut einen Sub-Agent mit dem aus der Role konfigurierten Modell.

    Returns:
        AgentRead mit model, system_prompt_preview, tools, etc.
        WICHTIG: Fuehrt KEIN LLM-Call aus, nur Aufbau.
    """
    from ..models.task import Task
    task = None
    if task_id:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(404, f"Task {task_id} nicht gefunden")

    try:
        agent = SubAgentService.build_agent(
            db, role_name=role_name, task=task, override_model=override_model
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return agent.to_dict()


@router.patch("/{role_name}/model", response_model=AgentConfigRead)
async def update_role_model(
    role_name: str,
    body: ModelUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktualisiert das Modell einer Rolle (User-Direktive 18.06.2026).

    Beispiel: PATCH /api/subagents/pi-coder/model
              Body: {"model": "ollama/gemma4:12b", "provider": "ollama"}
    """
    try:
        role = SubAgentService.update_role_model(db, role_name, body.model, body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Aktualisierte Config zurueckgeben
    configs = SubAgentService.list_agent_configs(db)
    for c in configs:
        if c["name"] == role_name:
            return c
    raise HTTPException(500, "Config nicht gefunden nach Update")


# === Sub-Agent-Spawning-Registry (User-Direktive 19.06.2026) ===
# Zeigt aktive Sub-Agent-Prozesse, die ueber spawn.sh gestartet wurden.
from ..services.sub_agent import (
    list_active_agents as _list_active,
    get_agent_for_task as _get_agent,
    cleanup_dead_agents as _cleanup_dead,
)
from ..models.task import Task as _Task


@router.get("/spawned/active")
async def list_active_agents_endpoint(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle aktuell laufenden Sub-Agent-Prozesse (via spawn.sh)."""
    agents = _list_active()
    return {"items": agents, "total": len(agents)}


@router.get("/spawned/for-task/{task_id}")
async def get_agent_for_task_endpoint(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert den Sub-Agent-Prozess fuer einen bestimmten Task."""
    t = db.get(_Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")

    info = _get_agent(task_id)
    if info:
        return {
            "task_id": task_id,
            "alive": True,
            "from_db": False,
            "pid": info["pid"],
            "role": info["role"],
            "spawned_at": info["spawned_at"],
            "log_path": info["log_path"],
        }
    # Fallback: aus DB meta
    meta = (t.meta or {}).get("sub_agent")
    if meta:
        return {"task_id": task_id, "alive": False, "from_db": True, **meta}
    raise HTTPException(404, "No sub-agent for this task")


@router.post("/spawned/cleanup")
async def cleanup_dead_agents_endpoint(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Entfernt abgestuerzte Sub-Agent-Prozesse aus der In-Memory-Registry."""
    cleaned = _cleanup_dead()
    return {"cleaned": cleaned, "remaining": len(_list_active())}
