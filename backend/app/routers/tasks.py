"""Tasks Router — komplett sauber (v2.0-rc)."""
from __future__ import annotations

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.task import (
    TaskRead, TaskCreate, TaskUpdate, TaskList, TaskStats,
    TaskStatusUpdate, TaskPriorityUpdate, TaskDispatchUpdate, TaskTokenReport,
    TaskHistoryEntry, TaskWithStats,
    SubTaskCreate, SubTaskCreateList,
)
from ..services.task_service import TaskService
from ..models.task import Task
from ..utils.status_labels import display_status, translate_history_details
from .. import events as _events

router = APIRouter(prefix="/api/kanban/tasks", tags=["tasks"])


@router.get("")  # kein response_model -> spart doppeltes Pydantic-Encoding
async def list_tasks(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    tasks = TaskService.list_tasks(db, project_id=project_id, status=status)
    paginated = tasks[offset:offset + limit]
    # Performance: direkter dict-Build statt model_validate (Pydantic-Overhead)
    items = []
    for t in paginated:
        items.append({
            "id": t.id, "title": t.title, "description": t.description or "",
            "status": t.status,
            "status_display": display_status(t.status),
            "priority": t.priority, "category": t.category,
            "assigned_role": t.assigned_role or "",
            "success_criteria": t.success_criteria or [],
            "tags": t.tags or [],
            "project_id": t.project_id or "",
            "parent_id": t.parent_id or "",
            "assigned_subagent": t.assigned_subagent or "",
            "iteration_count": t.iteration_count,
            "order": t.order,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "claimed_at": t.claimed_at.isoformat() if t.claimed_at else None,
            "emergency": t.emergency,
            "pricing_snapshot": t.pricing_snapshot,
            "meta": t.meta or {},
        })
    return {
        "items": items,
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    req: TaskCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.create_task(
        db, title=req.title, project_id=req.project_id, description=req.description,
        status=req.status, priority=req.priority, category=req.category,
        parent_id=req.parent_id, assigned_role=req.assigned_role,
    )
    await _events.publish_event(t.project_id or "", "task_created",
                                {"task_id": t.id, "title": t.title, "status": t.status})
    return TaskRead.model_validate(t)


@router.get("/{task_id}", response_model=TaskWithStats)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    # User-Direktive 18.06.2026: Fuzzy-Suche (LIKE) fuer teilweise task_ids
    t = TaskService.get_task(db, task_id)
    if not t and len(task_id) < 12:
        # Versuche LIKE-Suche
        from ..models.task import Task
        candidates = list(db.execute(
            select(Task).where(Task.id.like(f"{task_id}%")).limit(1)
        ).scalars())
        if candidates:
            t = candidates[0]
            task_id = t.id  # Volle ID fuer stats-Berechnung
    if not t:
        raise HTTPException(404, "Task not found")
    stats = TaskService.task_stats(db, task_id)
    # === User-Direktive 18.06.2026: status_display (z.B. 'todo' -> 'GO') ===
    task_dump = TaskRead.model_validate(t).model_dump()
    task_dump["status_display"] = display_status(t.status)
    return TaskWithStats(**task_dump, stats=TaskStats(**stats))


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    req: TaskUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.update_task(db, task_id, **req.model_dump(exclude_unset=True))
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


# ─────────────── CIO-Triage-Endpoints (Schritt 0, User-Direktive 16.06.2026) ───────────────

@router.put("/{task_id}/task-type", response_model=TaskRead)
async def set_task_type(
    task_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt den Task-Typ (vom CIO in Schritt 0 klassifiziert).

    Erlaubte Werte: new_request | change | ticket | bugfix
    """
    task_type = body.get("task_type")
    if task_type and task_type not in ("new_request", "change", "ticket", "bugfix"):
        raise HTTPException(400, f"Invalid task_type: {task_type}")
    t = TaskService.update_task(db, task_id, task_type=task_type)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/implementation-plan", response_model=TaskRead)
async def set_implementation_plan(
    task_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt den strukturierten Implementierungs-Plan (vom CIO in Schritt 0 ergaenzt).

    Body: { "implementation_plan": { "files": [...], "routes": [...], "api_changes": [...], "notes": "..." } }
    """
    plan = body.get("implementation_plan")
    if plan is not None and not isinstance(plan, dict):
        raise HTTPException(400, "implementation_plan must be an object")
    t = TaskService.update_task(db, task_id, implementation_plan=plan)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/standards-check", response_model=TaskRead)
async def set_standards_check(
    task_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt das Ergebnis der OpenBrain-Standardvorgaben-Pruefung (CIO bewertet).

    Body: { "standards_check": { "checked_at": "...", "matches": [...], "missing": [...], "notes": "..." } }
    """
    check = body.get("standards_check")
    if check is not None and not isinstance(check, dict):
        raise HTTPException(400, "standards_check must be an object")
    t = TaskService.update_task(db, task_id, standards_check=check)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/subagent-readiness", response_model=TaskRead)
async def set_subagent_readiness(
    task_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt die Subagent-Readiness-Bewertung (CIO prueft).

    Body: { "subagent_readiness": { "model": "...", "branch": "...", "context_files": [...], "ready": true } }
    """
    readiness = body.get("subagent_readiness")
    if readiness is not None and not isinstance(readiness, dict):
        raise HTTPException(400, "subagent_readiness must be an object")
    t = TaskService.update_task(db, task_id, subagent_readiness=readiness)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/status", response_model=TaskRead)
async def set_task_status(
    task_id: str,
    req: TaskStatusUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt Task-Status SOFORT neu (ohne 5s-Wartezeit im API-Call).

    Fruehere Variante: change_status_with_delay(delay_s=5.0) hat den API-Call
    fuer 5 Sekunden blockiert -> Browser hat das als "Fehler" interpretiert.

    Jetzt: set_status_sync + Background-Task fuer Auto-Claim/Watchdog.
    So bekommt der User sofort Feedback (Task wandert sichtbar in neue Spalte).

    NEU (User-Direktive 17.06.2026): Wenn der neue Status "triage" ist UND das
    Projekt eine default_sop_id hat, wird automatisch eine neue SOP-Instance
    gestartet (z.B. wenn User per Drag&Drop den Task zurueck in Triage schiebt).
    """
    # SOFORTIGE Status-Aenderung (synchron, kein 5s-Wait im API-Call)
    t = TaskService.set_status_sync(
        db, task_id, req.status,
        agent="user", reason="api_set_status", delay_s=0.0,
    )
    if not t:
        raise HTTPException(404, "Task not found")
    # Background-Task fuer spaetere Auto-Claim-Logik (nach 5s)
    if req.status == "todo":
        try:
            TaskService._schedule_background_delay(
                db, t, t.status, req.status, "user", "api_set_status", {}, 5.0
            )
        except Exception:
            pass
    await _events.publish_event(t.project_id or "", "task_status_changed",
                                {"task_id": t.id, "new_status": t.status, "priority": t.priority})

    # === NEU: Bei status=in_progress + assigned_subagent -> Sub-Agent spawnen (User-Direktive 19.06.2026) ===
    if t.status == "in_progress" and (t.assigned_subagent or t.assigned_role):
        import logging
        spawn_logger = logging.getLogger("pi-dashboard-2")
        try:
            from ..services.sub_agent import _spawn_sub_agent
            spawn_result = await _spawn_sub_agent(t, db)
            if spawn_result:
                spawn_logger.info(
                    f"Sub-Agent fuer Task {t.id[:8]} gestartet via set_status: "
                    f"PID {spawn_result.get('pid')}, Rolle {spawn_result.get('role')}"
                )
        except Exception as spawn_err:
            spawn_logger.error(
                f"Sub-Agent-Spawn fehlgeschlagen fuer Task {t.id[:8]}: {spawn_err}"
            )

    # === NEU: Bei status=triage -> default SOP neu starten ===
    sop_instance_id = None
    if t.status == "triage" and t.project_id:
        try:
            import secrets
            from ..models.project import Project
            from ..models.sop import SOPInstance
            proj = db.get(Project, t.project_id)
            if proj and proj.default_sop_id:
                # Pruefen ob schon eine laufende Instance existiert
                existing = db.execute(
                    select(SOPInstance).where(
                        SOPInstance.task_id == t.id,
                        SOPInstance.status.in_(["running", "pending", "waiting_sub_sop"]),
                    )
                ).scalar_one_or_none()
                if existing:
                    sop_instance_id = existing.id
                else:
                    # Erste Step der SOP holen (Fix User-Direktive 18.06.2026:
                    # current_step_id=None fuehrte zu "Instance is completed" Fehler)
                    from ..models.sop import SOPStep
                    first_step = db.execute(
                        select(SOPStep).where(SOPStep.sop_id == proj.default_sop_id)
                        .order_by(SOPStep.step_order).limit(1)
                    ).scalar_one_or_none()
                    # Neue SOP-Instance starten
                    new_inst = SOPInstance(
                        id=secrets.token_hex(6),  # explizite ID vergeben (NOT NULL constraint)
                        sop_id=proj.default_sop_id,
                        task_id=t.id,
                        project_id=t.project_id,
                        current_step_id=first_step.id if first_step else None,
                        status="running",
                    )
                    db.add(new_inst)
                    db.commit()
                    db.refresh(new_inst)
                    sop_instance_id = new_inst.id
                    # History-Eintrag
                    from ..models.history import TaskHistory
                    th = TaskHistory(
                        task_id=t.id,
                        event="sop_restarted",
                        agent="system",
                        details={"sop_id": proj.default_sop_id, "instance_id": new_inst.id, "reason": "status_reset_to_triage"},
                    )
                    db.add(th)
                    db.commit()
        except Exception as e:
            import logging
            logging.getLogger("pi-dashboard-2").warning(f"SOP-Restart fehlgeschlagen: {e}")
            db.rollback()

    # Response mit sop_instance_id (als JSON-Dict, nicht Pydantic-Model)
    import logging
    import json as json_lib
    logger = logging.getLogger("pi-dashboard-2")
    logger.info(f"[Drag&Drop] task={task_id} status={t.status} sop_instance_id={sop_instance_id}")
    # success_criteria und tags sind in der DB als JSON-Strings gespeichert -> parsen
    sc_val = t.success_criteria
    if isinstance(sc_val, str):
        try: sc_val = json_lib.loads(sc_val)
        except Exception: sc_val = []
    tags_val = t.tags
    if isinstance(tags_val, str):
        try: tags_val = json_lib.loads(tags_val)
        except Exception: tags_val = []
    # Build full dict with all required fields (umgeht Pydantic-Validierung)
    resp_dict = {
        "id": t.id,
        "title": t.title or "",
        "description": t.description or "",
        "status": t.status,
        "priority": t.priority or 50,
        "category": t.category,
        "assigned_role": t.assigned_role,
        "success_criteria": sc_val or [],
        "tags": tags_val or [],
        "project_id": t.project_id,
        "parent_id": t.parent_id,
        "assigned_subagent": t.assigned_subagent,
        "iteration_count": t.iteration_count or 0,
        "order": t.order or 0,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "claimed_at": t.claimed_at.isoformat() if t.claimed_at else None,
        "emergency": t.emergency or False,
        "pricing_snapshot": t.pricing_snapshot,
        "meta": t.meta or {},
        "task_type": t.task_type,
        "implementation_plan": t.implementation_plan,
        "standards_check": t.standards_check,
        "subagent_readiness": t.subagent_readiness,
    }
    if sop_instance_id:
        resp_dict["sop_instance_id"] = sop_instance_id
        logger.info(f"[Drag&Drop] Response mit sop_instance_id={sop_instance_id}")
    return resp_dict


@router.put("/{task_id}/priority", response_model=TaskRead)
async def set_task_priority(
    task_id: str,
    req: TaskPriorityUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.set_priority(db, task_id, req.priority)
    if not t:
        raise HTTPException(404, "Task not found")
    await _events.publish_event(t.project_id or "", "task_priority_changed",
                                {"task_id": t.id, "new_priority": t.priority, "emergency": t.emergency})
    return TaskRead.model_validate(t)


@router.patch("/{task_id}/dispatch", response_model=dict)
async def report_dispatch(
    task_id: str,
    req: TaskDispatchUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    result = TaskService.report_dispatch(
        db, task_id, role=req.role or "subagent", status=req.status or "dispatched",
        model=req.model or "minimax/minimax-m3",
        agent_pid=req.agent_pid, reason=req.reason,
        tokens_in=req.tokens_in, tokens_out=req.tokens_out,
    )
    if not result:
        raise HTTPException(404, "Task not found")
    return result


@router.post("/{task_id}/usage", response_model=dict)
async def report_usage(
    task_id: str,
    req: TaskTokenReport,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    result = TaskService.report_usage(
        db, task_id, tokens_in=req.tokens_in, tokens_out=req.tokens_out,
        model=req.model, role=req.role, note=req.note,
    )
    if not result:
        raise HTTPException(404, "Task not found")
    if result.get("task_id"):
        t = TaskService.get_task(db, result["task_id"])
        if t:
            await _events.publish_event(t.project_id or "", "task_usage_reported",
                                        {"task_id": t.id, "cost_usd": result.get("cost_usd"),
                                         "tokens_in": result.get("tokens_in"),
                                         "tokens_out": result.get("tokens_out")})
    return result


@router.get("/{task_id}/stats", response_model=TaskStats)
async def get_task_stats(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    stats = TaskService.task_stats(db, task_id)
    if not stats:
        raise HTTPException(404, "Task not found")
    return TaskStats(**stats)


@router.get("/{task_id}/sop-status", response_model=dict)
async def get_task_sop_status(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """SOP-Status fuer einen Task: aktueller Step, Verantwortlicher, naechster Step, Fortschritt.

    User-Direktive 18.06.2026: Das TaskDetailPanel soll anzeigen, in welchem
    SOP-Step der Task gerade ist, wer dafuer verantwortlich ist und was als
    naechstes passiert. Diese Daten kommen aus der SOP-Instance + SOP-Definition.

    Response:
    {
        "task_id": "...",
        "sop_id": "7c86692be939",
        "sop_name": "Standard-Workflow Development",
        "instance_id": "...",
        "instance_status": "running" | "completed" | None,
        "current_step": {
            "id": "13199b7c2b40",
            "order": 1,
            "name": "Worker Assignment",
            "agent": "CIO",
            "phase": "Task",
            "action": "assign_worker"
        } | None,
        "next_step": {
            "id": "bd79e783d050",
            "order": 2,
            "name": "Worker Implementation",
            "agent": "pi-coder"
        } | None,
        "total_steps": 6,
        "completed_steps": 1,
        "progress_pct": 17,  # 1/6 * 100
        "all_steps": [
            {"order": 0, "name": "CIO Triage Review", "agent": "CIO"},
            ...
        ]
    }
    """
    from ..models.sop import SOP, SOPStep, SOPInstance

    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")

    # Aktuelle Instance finden (neueste laufende oder completed)
    instances = list(db.execute(
        select(SOPInstance)
        .where(SOPInstance.task_id == task_id)
        .order_by(SOPInstance.started_at.desc())
    ).scalars())
    instance = next(
        (i for i in instances if i.status in ("running", "completed")),
        None
    )
    if not instance:
        return {
            "task_id": task_id,
            "sop_id": None,
            "sop_name": None,
            "instance_id": None,
            "instance_status": None,
            "current_step": None,
            "next_step": None,
            "total_steps": 0,
            "completed_steps": 0,
            "progress_pct": 0,
            "all_steps": [],
            "note": "Keine SOP-Instance vorhanden. Task wurde noch nicht in eine SOP eingebunden.",
        }

    sop = db.get(SOP, instance.sop_id)
    if not sop:
        raise HTTPException(500, f"SOP {instance.sop_id} nicht gefunden")

    # Alle Steps sortiert
    all_steps_db = list(db.execute(
        select(SOPStep)
        .where(SOPStep.sop_id == instance.sop_id)
        .order_by(SOPStep.step_order)
    ).scalars())
    all_steps = [
        {"order": s.step_order, "id": s.id, "name": s.name, "agent": s.agent, "phase": s.phase}
        for s in all_steps_db
    ]

    # Aktueller Step
    current_step = None
    completed_count = 0
    if instance.current_step_id and instance.status == "running":
        cur = next((s for s in all_steps_db if s.id == instance.current_step_id), None)
        if cur:
            current_step = {
                "id": cur.id,
                "order": cur.step_order,
                "name": cur.name,
                "agent": cur.agent,
                "phase": cur.phase,
                "action": cur.action,
            }
            completed_count = cur.step_order
    elif instance.status == "completed":
        # Instance ist fertig -> alle Steps erfuellt
        completed_count = len(all_steps_db)

    # Naechster Step
    next_step = None
    if current_step and current_step["order"] + 1 < len(all_steps_db):
        nxt = all_steps_db[current_step["order"] + 1]
        next_step = {
            "id": nxt.id,
            "order": nxt.step_order,
            "name": nxt.name,
            "agent": nxt.agent,
        }

    progress_pct = int(completed_count / max(len(all_steps_db), 1) * 100)

    return {
        "task_id": task_id,
        "sop_id": instance.sop_id,
        "sop_name": sop.name if sop else None,
        "instance_id": instance.id,
        "instance_status": instance.status,
        "current_step": current_step,
        "next_step": next_step,
        "total_steps": len(all_steps_db),
        "completed_steps": completed_count,
        "progress_pct": progress_pct,
        "all_steps": all_steps,
    }


@router.get("/{task_id}/history", response_model=dict)
async def get_task_history(
    task_id: str,
    limit: int = Query(100),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    from ..models.history import TaskHistory
    # User-Direktive 18.06.2026: Fuzzy-Suche (LIKE) fuer teilweise task_ids
    if len(task_id) < 12:
        history = list(db.execute(
            select(TaskHistory).where(TaskHistory.task_id.like(f"{task_id}%"))
            .order_by(TaskHistory.ts.desc()).limit(limit)
        ).scalars())
    else:
        history = list(db.execute(
            select(TaskHistory).where(TaskHistory.task_id == task_id)
            .order_by(TaskHistory.ts.desc()).limit(limit)
        ).scalars())
    # === User-Direktive 18.06.2026: details-Mapping (z.B. 'todo' -> 'GO') ===
    # Das DB-Audit-Log bleibt unveraendert (interne Identitaet), aber die
    # Response hat zusaetzlich 'details_mapped' mit Display-Namen.
    items = []
    for h in history:
        entry = TaskHistoryEntry.model_validate(h).model_dump()
        entry["details_mapped"] = translate_history_details(entry.get("details", {}))
        items.append(entry)
    return {
        "task_id": task_id,
        "history": items,
        "stats": TaskService.task_stats(db, task_id),
    }


@router.post("/{task_id}/subtasks", response_model=List[TaskRead], status_code=201)
async def create_subtasks(
    task_id: str,
    req: SubTaskCreateList = Body(...),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Erstellt Sub-Tasks fuer eine Parent-Task."""
    parent = TaskService.get_task(db, task_id)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    created = []
    for st in req.subtasks:
        sub = TaskService.create_task(
            db, title=st.title, project_id=parent.project_id,
            description=st.description, priority=st.priority, category=st.category,
            parent_id=task_id, assigned_role=st.assigned_role,
        )
        created.append(sub)
    db.commit()
    return [TaskRead.model_validate(s) for s in created]


@router.post("/{task_id}/aggregate", response_model=TaskRead)
async def aggregate_subtasks(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aggregiert Sub-Task-Status zum Parent."""
    parent = TaskService.get_task(db, task_id)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    subs = list(db.execute(select(Task).where(Task.parent_id == task_id)).scalars())
    if not subs:
        raise HTTPException(400, "Task hat keine Sub-Tasks")
    statuses = [s.status for s in subs]
    if all(s == "done" for s in statuses):
        new_status = "done"
    elif any(s == "warten" for s in statuses):
        new_status = "warten"
    elif any(s == "in_progress" for s in statuses):
        new_status = "in_progress"
    elif all(s == "review" for s in statuses):
        new_status = "review"
    else:
        return TaskRead.model_validate(parent)
    parent.status = new_status
    parent.updated_at = datetime.utcnow()
    TaskService._add_history(db, parent, "subtasks_aggregated", agent="system",
                             details={"new_status": new_status, "sub_count": len(subs)})
    # Task-Transition-Record + 5s Background-Delay (User-Direktive 16.06.2026)
    TaskService._do_set_status_sync_body(
        db, parent, old_status=parent.status, new_status=new_status,
        agent="system", reason="subtasks_aggregated",
        details={"new_status": new_status, "sub_count": len(subs)},
        delay_s=5.0,
    )
    return TaskRead.model_validate(parent)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    ok = TaskService.delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")


# === NewTask-AI-Validation (User-Direktive 17.06.2026) ===
# Prueft die User-Beschreibung und stellt Rueckfragen, damit der Task moeglichst
# ohne weitere Rueckfragen durch den Triage-Prozess laeuft.
class TaskValidationRequest(BaseModel):
    title: str
    description: str
    category: Optional[str] = None
    priority: Optional[int] = None
    project_id: Optional[str] = None


class TaskValidationResponse(BaseModel):
    ok: bool
    score: int  # 0-100, wie gut der Task bereits beschrieben ist
    quality_issues: List[str]  # Was fehlt oder unklar ist
    suggested_criteria: List[str]  # 1-3 vorgeschlagene Erfolgskriterien (NICHT mehr)
    suggested_title: Optional[str] = None  # Verbesserter Titel-Vorschlag
    suggested_category: Optional[str] = None
    suggested_priority: Optional[int] = None
    refinement_questions: List[str]  # Rueckfragen zur Verbesserung
    ready_to_create: bool  # True, wenn der Task ohne weitere Rueckfragen erstellt werden kann


@router.post("/validate-with-llm", response_model=TaskValidationResponse)
async def validate_task_with_llm(req: TaskValidationRequest):
    """Laesst die KI die Task-Beschreibung pruefen und Verbesserungen vorschlagen.

    Ziel: Bestmoegliche Task-Description, damit der Task nach Triage OHNE
    weitere Rueckfragen durch den Prozess laeuft.
    """
    import json
    import logging
    from ..services.llm_service import chat_completion

    logger = logging.getLogger("pi-dashboard-2")

    # Wenn title/description zu kurz sind, direkt ablehnen
    if not req.title or len(req.title) < 5:
        return TaskValidationResponse(
            ok=False,
            score=0,
            quality_issues=["Titel ist zu kurz oder fehlt"],
            suggested_criteria=[],
            suggested_title=req.title,
            suggested_category=req.category,
            suggested_priority=req.priority,
            refinement_questions=["Was ist der genaue Titel der Aufgabe? (min 5 Zeichen)"],
            ready_to_create=False,
        )

    if not req.description or len(req.description) < 50:
        return TaskValidationResponse(
            ok=False,
            score=20,
            quality_issues=["Description ist zu kurz (min 50 Zeichen)"],
            suggested_criteria=[],
            suggested_title=req.title,
            suggested_category=req.category,
            suggested_priority=req.priority,
            refinement_questions=[
                "Beschreibe die Aufgabe genauer: Was soll gemacht werden?",
                "Welche Akzeptanzkriterien gibt es?",
            ],
            ready_to_create=False,
        )

    # LLM-Call: Pruefe die Task-Beschreibung
    system_prompt = """Du bist ein erfahrener PI-CIO, der neue Tasks prueft, BEVOR sie in die Triage gehen. Deine Aufgabe ist es, die User-Beschreibung zu analysieren und sicherzustellen, dass der Task moeglichst ohne Rueckfragen durch den Triage-Prozess laufen kann.

**Pruefe diese 5 Dimensionen:**
1. **Vollstaendigkeit**: Sind Title + Description ausreichend detailliert?
2. **Klarheit**: Ist klar, WAS erreicht werden soll und WIE?
3. **Akzeptanzkriterien**: Sind 1-3 testbare Kriterien erkennbar oder ableitbar? (NICHT mehr als 3, weil der Worker sonst ueberfordert ist)
4. **Rollen**: Welche Worker-Rollen (pi-coder, pi-tester, etc.) sind noetig?
5. **Stabilitaet/Sicherheit**: Sind negative Effekte auf Stabilitaet oder Security erkennbar?

**Antwort-Format (STRIKTES JSON, nichts anderes):**
```json
{
  "score": 0-100,
  "quality_issues": ["Liste der Probleme, leer wenn alles OK"],
  "suggested_criteria": ["Kriterium 1", "Kriterium 2"],
  "suggested_title": "Verbesserter Titel-Vorschlag (oder gleich wie Original)",
  "suggested_category": "bugfix|new_request|change|...",
  "suggested_priority": 1-100,
  "refinement_questions": ["Frage 1", "Frage 2"],
  "ready_to_create": true/false
}
```

**Wichtig:**
- Score >= 80 = ready_to_create=true
- MAXIMAL 1-3 Kriterien, jede MESSBAR und TESTBAR (NICHT mehr als 3!)
- Anstatt 'Login funktioniert' lieber 'User kann sich mit OAuth2-Provider einloggen, Tests gruen'
- Anstatt 'Code ist sauber' lieber 'Coverage > 80%'
- Sprache: Deutsch
"""

    user_prompt = f"""**Task-Titel:** {req.title}

**Task-Description:**
{req.description}

**Aktuelle Kategorie:** {req.category or '(nicht gesetzt)'}
**Aktuelle Prioritaet:** {req.priority or '(nicht gesetzt)'}
**Aktuelles Projekt-ID:** {req.project_id or '(nicht gesetzt)'}

Pruefe diesen Task und schlage Verbesserungen vor."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = await chat_completion(
            messages=messages,
            model="minimax-m3",
            temperature=0.3,
            max_tokens=2000,
        )
        # Content extrahieren
        if isinstance(result, dict):
            content = result.get("content", result.get("text", str(result)))
        else:
            content = str(result)

        # JSON extrahieren
        import re
        # Versuche direkt
        try:
            data = json.loads(content)
        except Exception:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
            else:
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(content[start : end + 1])
                else:
                    data = {}

        return TaskValidationResponse(
            ok=data.get("ready_to_create", False),
            score=data.get("score", 50),
            quality_issues=data.get("quality_issues", []),
            suggested_criteria=data.get("suggested_criteria", []),
            suggested_title=data.get("suggested_title", req.title),
            suggested_category=data.get("suggested_category", req.category),
            suggested_priority=data.get("suggested_priority", req.priority),
            refinement_questions=data.get("refinement_questions", []),
            ready_to_create=data.get("ready_to_create", False),
        )
    except Exception as e:
        logger.error(f"LLM-Validation fehlgeschlagen: {e}")
        # Fallback: Task kann erstellt werden
        return TaskValidationResponse(
            ok=True,
            score=50,
            quality_issues=["LLM-Validation fehlgeschlagen"],
            suggested_criteria=[
                f"Task '{req.title}' ist vollstaendig implementiert",
                "Bestehende Unit-Tests laufen alle gruen",
                "Doku wurde aktualisiert",
                "Code-Review wurde durchgefuehrt",
            ],
            suggested_title=req.title,
            suggested_category=req.category,
            suggested_priority=req.priority,
            refinement_questions=[],
            ready_to_create=True,
        )


# === Bulk-Triage: alle Tasks eines Projekts zurueck in Triage ===
@router.post("/bulk-triage/{project_id}")
async def bulk_set_tasks_triage(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt ALLE Tasks eines Projekts auf Status 'triage'."""
    tasks = list(db.execute(
        select(Task).where(Task.project_id == project_id)
    ).scalars())
    count = 0
    for t in tasks:
        if t.status != "triage":
            old = t.status
            t.status = "triage"
            t.updated_at = datetime.utcnow()
            TaskService._add_history(db, t, "status_changed", agent="system",
                                     details={"from": old, "to": "triage", "reason": "bulk_triage"})
            # Task-Transition-Record + 5s Background-Delay (User-Direktive 16.06.2026)
            TaskService._do_set_status_sync_body(
                db, t, old_status=old, new_status="triage",
                agent="system", reason="bulk_triage",
                details={"from": old, "to": "triage"},
                delay_s=5.0,
            )
            count += 1
    return {"ok": True, "project_id": project_id, "reset_to_triage": count, "total": len(tasks)}


# === Auto-Process-Triage: Prio + Role basierend auf Description setzen ===
@router.post("/triage/{project_id}/process")
async def process_triage(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Process Triage: setzt Prio basierend auf Description-Laenge.

    Logik (User-Direktive 18.06.2026):
    - Prio: desc > 500 -> 75, > 200 -> 50, sonst -> 25
    - Role: NICHT mehr setzen! Die SOP-Engine (Step 0/1/2/3) setzt assigned_role
      pro Step. Waehrend Triage ist assigned_role = None (CIO bewertet).
    - Tools: read, write, bash, grep
    - needs_breakdown: desc > 800
    """
    tasks = list(db.execute(
        select(Task).where(
            Task.project_id == project_id,
            Task.status == "triage"
        )
    ).scalars())
    processed = 0
    for t in tasks:
        desc = (t.description or "").lower()
        desc_len = len(t.description or "")
        old_status = t.status
        t.priority = 75 if desc_len > 500 else 50 if desc_len > 200 else 25
        # assigned_role wird NICHT mehr hier gesetzt. SOP-Engine (Step 0 = CIO,
        # Step 1 = CIO, Step 2 = pi-coder, Step 3 = pi-tester) setzt ihn pro Step.
        t.status = "todo"
        t.updated_at = datetime.utcnow()
        TaskService._add_history(db, t, "status_changed", agent="system",
                                 details={"from": old_status, "to": "todo", "reason": "process_triage",
                                          "new_priority": t.priority, "new_role": t.assigned_role})
        # Task-Transition-Record + 5s Background-Delay (User-Direktive 16.06.2026)
        TaskService._do_set_status_sync_body(
            db, t, old_status=old_status, new_status="todo",
            agent="system", reason="process_triage",
            details={"from": old_status, "to": "todo",
                     "new_priority": t.priority, "new_role": t.assigned_role},
            delay_s=5.0,
        )
        processed += 1
    db.commit()
    return {"ok": True, "project_id": project_id, "processed": processed}
