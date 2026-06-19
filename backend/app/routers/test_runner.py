"""TestRunner-Router: Navigator-Service fuer Test-Aktionen.

User-Direktive 17.06.2026:
  Zentraler Service, der vom "Test Tool" im Navigator aufgerufen wird.
  Listet verfuegbare Aktionen und fuehrt sie aus.

Aktionen:
  - start-iscp: Startet die ISCP-SOP, erstellt einen Task in SpecCreator

Endpunkte:
  GET  /api/test-runner/actions                  — Liste der verfuegbaren Aktionen
  POST /api/test-runner/actions/{action_id}      — Aktion ausfuehren
  GET  /api/test-runner/history                  — Ausfuehrungs-History
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db, SessionLocal
from ..models.project import Project
from ..models.sop import SOP, SOPStep, SOPInstance
from ..models.task import Task
from ..models.history import TaskHistory

logger = logging.getLogger("pi-dashboard-2.test-runner")
router = APIRouter(prefix="/api/test-runner", tags=["test-runner"])


# === Action-Definitionen ===
# Jede Aktion: id, title, description, icon, params_schema, handler
ACTIONS: Dict[str, Dict[str, Any]] = {
    "start-iscp": {
        "id": "start-iscp",
        "title": "SOP / ISCP starten",
        "description": "Startet die ISCP-SOP (IT-Spec Creation Process) und erstellt einen frischen Task im SpecCreator-Projekt. Der erste Step (CEO-digital) wird sofort ausgefuehrt und fordert initialen Input vom User.",
        "icon": "file-text",
        "category": "sop",
        "params_schema": {
            "task_title": {"type": "string", "required": False,
                           "default": "IT-Spec erstellen",
                           "description": "Titel des neuen Tasks im SpecCreator"},
            "task_description": {"type": "text", "required": False,
                                 "default": "Spec-Erstellung via ISCP-SOP",
                                 "description": "Beschreibung des neuen Tasks"},
            "sop_id": {"type": "string", "required": False, "default": "f563552f72eb",
                       "description": "ID der zu startenden SOP"},
            "project_name": {"type": "string", "required": False, "default": "SpecCreator",
                             "description": "Name des Ziel-Projekts"},
        },
    },
}


# === History (in-memory, koennte spaeter in DB) ===
_HISTORY: List[Dict[str, Any]] = []


def _log_history(action_id: str, params: dict, result: dict) -> None:
    _HISTORY.append({
        "ts": datetime.utcnow().isoformat(),
        "action_id": action_id,
        "params": params,
        "result": result,
    })
    # Max 100 Eintraege
    while len(_HISTORY) > 100:
        _HISTORY.pop(0)


# === Endpoints ===

@router.get("/actions")
async def list_actions(
    user: str = Depends(require_auth),
) -> dict:
    """Liste aller verfuegbaren Test-Aktionen."""
    return {
        "actions": list(ACTIONS.values()),
        "total": len(ACTIONS),
    }


@router.get("/actions/{action_id}")
async def get_action(
    action_id: str,
    user: str = Depends(require_auth),
) -> dict:
    """Detail einer einzelnen Aktion."""
    if action_id not in ACTIONS:
        raise HTTPException(404, f"Action {action_id!r} nicht gefunden")
    return ACTIONS[action_id]


class ActionExecute(BaseModel):
    params: Dict[str, Any] = {}


@router.post("/actions/{action_id}/execute")
async def execute_action(
    action_id: str,
    body: ActionExecute,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Eine Aktion ausfuehren."""
    if action_id not in ACTIONS:
        raise HTTPException(404, f"Action {action_id!r} nicht gefunden")

    if action_id == "start-iscp":
        result = await _execute_start_iscp(db, body.params)
    else:
        raise HTTPException(400, f"Action {action_id!r} hat noch keinen Handler")

    _log_history(action_id, body.params, result)
    return result


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    user: str = Depends(require_auth),
) -> dict:
    """Letzte Action-Ausfuehrungen."""
    items = list(reversed(_HISTORY[-limit:]))
    return {
        "items": items,
        "total": len(_HISTORY),
    }


# === Handler: start-iscp ===

async def _execute_start_iscp(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handler fuer start-iscp-Aktion.

    Schritte:
      1) SpecCreator-Projekt finden (per Name)
      2) Task im SpecCreator erstellen
      3) SOP-Instance starten mit Task-Referenz
      4) Engine in den Hintergrund schicken (blockt auf User-Input)
    """
    project_name = params.get("project_name", "SpecCreator")
    sop_id = params.get("sop_id", "f563552f72eb")
    task_title = params.get("task_title", "IT-Spec erstellen")
    task_description = params.get("task_description", "Spec-Erstellung via ISCP-SOP")

    # 1) Projekt finden
    project = db.execute(
        select(Project).where(Project.name == project_name)
    ).scalar_one_or_none()
    if not project:
        # Auto-create SpecCreator
        project = Project(
            id=secrets.token_hex(6),
            name=project_name,
            description=f"Auto-erstellt vom TestRunner fuer {project_name}",
            status="active",
            mode="execution",  # Direkt auf execution
            category="new_request",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        created_project = True
    else:
        created_project = False

    # 2) SOP pruefen
    sop = db.get(SOP, sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id!r} nicht gefunden")

    # 3) Task erstellen
    task = Task(
        id=secrets.token_hex(6),
        project_id=project.id,
        title=task_title,
        description=task_description,
        status="triage",
        priority=50,
        category="new_request",
        assigned_role="CEO-digital",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # TaskHistory: Task erstellt
    history = TaskHistory(
        task_id=task.id,
        event="task_created",
        agent="test-runner",
        details={
            "created_by": "test-runner.start-iscp",
            "action": "start-iscp",
            "sop_id": sop_id,
            "project_name": project_name,
        },
    )
    db.add(history)
    db.commit()

    # 4) SOP-Instance starten
    from ..services.sop_engine import SOPEngine
    engine = SOPEngine(db)
    instance = engine.create_instance(
        sop_id=sop_id,
        project_id=project.id,
        task_id=task.id,
        context={},
    )
    if not instance:
        raise HTTPException(400, "Konnte SOP-Instance nicht starten")

    # 5) Engine asynchron starten (blockiert auf User-Input, falls Step 0 das verlangt)
    import asyncio
    asyncio.create_task(_run_step_async(instance.id, sop_id))

    return {
        "ok": True,
        "action": "start-iscp",
        "project": {
            "id": project.id,
            "name": project.name,
            "created": created_project,
        },
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "assigned_role": task.assigned_role,
        },
        "sop": {
            "id": sop.id,
            "name": sop.name,
        },
        "instance": {
            "id": instance.id,
            "status": instance.status,
            "current_step_id": instance.current_step_id,
            "current_step_name": next(
                (s.name for s in sop.steps if s.id == instance.current_step_id),
                None
            ),
        },
        "next_action": (
            "User muss die offene Frage im Tools-Tab beantworten. "
            "Die Frage wurde automatisch erstellt und wartet auf Input."
        ),
    }


async def _run_step_async(instance_id: str, sop_id: str) -> None:
    """Startet run_step in einer eigenen Session (blockt ggf. auf User-Input)."""
    from ..services.sop_engine import SOPEngine
    try:
        with SessionLocal() as db:
            engine = SOPEngine(db)
            instance = db.get(SOPInstance, instance_id)
            if instance and instance.status == "running":
                result = await engine.run_step(instance)
                logger.info(f"[test-runner] Instance {instance_id[:8]} run_step result: {result.get('ok')}")
    except Exception as e:
        logger.error(f"[test-runner] Background-run_step failed: {e}", exc_info=True)
